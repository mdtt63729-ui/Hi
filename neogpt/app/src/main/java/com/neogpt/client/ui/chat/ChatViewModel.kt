package com.neogpt.client.ui.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.neogpt.client.AppContainer
import com.neogpt.client.domain.model.Attachment
import com.neogpt.client.domain.model.Conversation
import com.neogpt.client.domain.model.Message
import com.neogpt.client.domain.model.Role
import com.neogpt.client.network.CompletionEvent
import com.neogpt.client.network.CompletionMessage
import com.neogpt.client.network.CompletionRequest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ChatUiState(
    val conversation: Conversation? = null,
    val messages: List<Message> = emptyList(),
    val input: String = "",
    val attachments: List<Attachment> = emptyList(),
    val isStreaming: Boolean = false,
    val modelId: String = "gpt-5",
    val providerConfigured: Boolean = false,
    val sendOnEnter: Boolean = true,
    val loading: Boolean = true,
    val conversationRemoved: Boolean = false,
)

class ChatViewModel(
    private val container: AppContainer,
    private val conversationId: String,
) : ViewModel() {

    private val _state = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _state.asStateFlow()

    private var streamJob: Job? = null

    init {
        viewModelScope.launch {
            container.preferences.preferences.collect { prefs ->
                _state.update {
                    it.copy(
                        modelId = prefs.modelId,
                        providerConfigured = prefs.isProviderConfigured,
                        sendOnEnter = prefs.sendOnEnter,
                    )
                }
            }
        }
        viewModelScope.launch {
            container.conversationRepository.observeConversation(conversationId).collect { conversation ->
                _state.update { current ->
                    when {
                        conversation != null -> current.copy(conversation = conversation)
                        current.conversation != null -> current.copy(
                            conversation = null,
                            conversationRemoved = true,
                            isStreaming = false,
                        )
                        else -> current
                    }
                }
            }
        }
        viewModelScope.launch {
            val existing = container.conversationRepository.messages(conversationId)
            _state.update { it.copy(messages = existing, loading = false) }
            if (existing.isNotEmpty() && existing.last().role == Role.USER) {
                generate()
            }
        }
    }

    fun setInput(value: String) {
        _state.update { it.copy(input = value) }
    }

    fun addAttachment(attachment: Attachment) {
        _state.update { current ->
            if (current.attachments.any { it.uri == attachment.uri }) current
            else current.copy(attachments = current.attachments + attachment)
        }
    }

    fun removeAttachment(attachment: Attachment) {
        _state.update { it.copy(attachments = it.attachments.filterNot { a -> a.uri == attachment.uri }) }
    }

    fun send() {
        val current = _state.value
        val text = current.input.trim()
        if (text.isEmpty() && current.attachments.isEmpty()) return
        if (current.isStreaming) return
        if (current.conversationRemoved) return

        val userMessage = Message(
            conversationId = conversationId,
            role = Role.USER,
            content = text,
            createdAt = System.currentTimeMillis(),
            attachments = current.attachments,
        )

        _state.update {
            it.copy(
                messages = it.messages + userMessage,
                input = "",
                attachments = emptyList(),
            )
        }

        viewModelScope.launch {
            container.conversationRepository.insertMessage(userMessage)
            container.conversationRepository.touchConversation(conversationId, userMessage.createdAt)
            generate()
        }
    }

    fun stop() {
        streamJob?.cancel()
    }

    fun setFeedback(messageId: String, value: Int) {
        _state.update { state ->
            state.copy(messages = state.messages.map { if (it.id == messageId) it.copy(feedback = value) else it })
        }
        viewModelScope.launch {
            container.conversationRepository.setFeedback(messageId, value)
        }
    }

    fun regenerate(messageId: String) {
        if (_state.value.isStreaming) return
        viewModelScope.launch {
            val messages = _state.value.messages
            val target = messages.firstOrNull { it.id == messageId } ?: return@launch
            val toDelete = messages.filter { it.role == Role.ASSISTANT && it.createdAt >= target.createdAt }
            container.conversationRepository.deleteMessages(toDelete.map { it.id })
            _state.update { it.copy(messages = messages.filterNot { m -> toDelete.any { it.id == m.id } }) }
            generate()
        }
    }

    private fun generate() {
        if (_state.value.isStreaming) return
        streamJob = viewModelScope.launch {
            try {
                runGeneration()
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (t: Throwable) {
                withContext(NonCancellable) {
                    appendFailure(t.message ?: "The request failed.")
                }
            }
        }
    }

    private suspend fun runGeneration() {
        val prefs = container.preferences.preferences.first()
        if (!prefs.isProviderConfigured) {
            appendFailure("Connect a provider in Settings to get answers.")
            return
        }

        val conversationHistory = _state.value.messages
            .filter { it.role != Role.SYSTEM && !it.streaming && it.error == null }
            .map { message ->
                CompletionMessage(
                    role = message.role.name.lowercase(),
                    content = message.content.withAttachmentNote(message.attachments),
                )
            }
        if (conversationHistory.isEmpty()) return
        val presentationInstructions = """
            You are answering inside NeoGPT, an Android chat app.
            Format responses with standard Markdown: use **bold** for emphasis, headings,
            readable paragraphs, lists, blockquotes, links, and fenced code blocks with a
            language label. Keep formatting valid while streaming.
            When a compact visual card genuinely improves the answer, you may emit this
            exact safe UI-card format (one JSON object, no HTML or scripts):
            ```neoui
            {"type":"card","title":"Card title","subtitle":"Short explanation","items":["First item","Second item"],"action":"Optional non-clickable label"}
            ```
            Use at most 8 concise items. Do not emit neoui for ordinary prose. Never claim
            that a UI card action is clickable; it is display-only. Do not wrap the entire
            answer in a code fence. Do not reveal hidden chain-of-thought; provide concise
            conclusions or brief summaries of reasoning instead.
        """.trimIndent()
        val history = listOf(CompletionMessage("system", presentationInstructions)) + conversationHistory

        val model = prefs.modelId
        val assistant = Message(
            conversationId = conversationId,
            role = Role.ASSISTANT,
            content = "",
            createdAt = System.currentTimeMillis(),
            streaming = true,
            modelId = model,
        )
        _state.update { it.copy(messages = it.messages + assistant, isStreaming = true) }

        val builder = StringBuilder()
        var failure: String? = null
        try {
            container.chatClient.streamCompletion(
                CompletionRequest(
                    baseUrl = prefs.baseUrl,
                    apiKey = prefs.apiKey,
                    model = model,
                    messages = history,
                )
            ).collect { event ->
                when (event) {
                    is CompletionEvent.Delta -> {
                        builder.append(event.text)
                        updateStreamingContent(assistant.id, builder.toString())
                    }

                    CompletionEvent.Completed -> Unit
                }
            }
            if (builder.isEmpty()) failure = "The model returned an empty response."
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (t: Throwable) {
            failure = t.message ?: "The request failed."
        } finally {
            withContext(NonCancellable) {
                finish(assistant.id, builder.toString(), failure)
            }
        }
    }

    private fun updateStreamingContent(id: String, text: String) {
        _state.update { state ->
            state.copy(messages = state.messages.map { if (it.id == id) it.copy(content = text) else it })
        }
    }

    private suspend fun finish(id: String, text: String, error: String?) {
        val message = _state.value.messages.firstOrNull { it.id == id } ?: return
        val final = message.copy(content = text, streaming = false, error = error)
        _state.update { state ->
            state.copy(
                messages = state.messages.map { if (it.id == id) final else it },
                isStreaming = false,
            )
        }
        container.conversationRepository.updateMessage(final)
        container.conversationRepository.touchConversation(conversationId, System.currentTimeMillis())
    }

    private suspend fun appendFailure(message: String) {
        val assistant = Message(
            conversationId = conversationId,
            role = Role.ASSISTANT,
            content = "",
            createdAt = System.currentTimeMillis(),
            error = message,
        )
        _state.update { it.copy(messages = it.messages + assistant, isStreaming = false) }
        container.conversationRepository.insertMessage(assistant)
    }

    private fun String.withAttachmentNote(attachments: List<Attachment>): String {
        if (attachments.isEmpty()) return this
        val note = attachments.joinToString("\n") { attachment ->
            val kind = if (attachment.isImage) "image" else "file"
            "[Attached $kind: ${attachment.name} (${attachment.mimeType})]"
        }
        return if (isBlank()) note else "$this\n\n$note"
    }
}
