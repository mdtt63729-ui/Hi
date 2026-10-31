package com.neogpt.client.ui.chat.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.ThumbDown
import androidx.compose.material.icons.rounded.ThumbUp
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.neogpt.client.domain.model.Attachment
import com.neogpt.client.domain.model.Message
import com.neogpt.client.domain.model.Role
import com.neogpt.client.ui.components.ThinkingIndicator
import com.neogpt.client.ui.components.NeoIconButton
import com.neogpt.client.ui.components.StreamingCursor
import com.neogpt.client.ui.theme.NeoTheme
import com.neogpt.client.ui.theme.UserBubbleShape

@Composable
fun MessageRow(
    message: Message,
    onFeedback: (Int) -> Unit,
    onRegenerate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    when (message.role) {
        Role.USER -> UserMessage(message = message, modifier = modifier)
        else -> AssistantMessage(
            message = message,
            onFeedback = onFeedback,
            onRegenerate = onRegenerate,
            modifier = modifier,
        )
    }
}

@Composable
private fun UserMessage(message: Message, modifier: Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.End,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .clip(UserBubbleShape)
                .background(NeoTheme.colors.userBubble)
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            message.attachments.forEach { attachment ->
                AttachmentPreview(attachment)
            }
            if (message.content.isNotBlank()) {
                Text(
                    text = message.content,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

@Composable
private fun AttachmentPreview(attachment: Attachment) {
    if (attachment.isImage) {
        AsyncImage(
            model = attachment.uri,
            contentDescription = attachment.name,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .size(width = 220.dp, height = 150.dp)
                .clip(RoundedCornerShape(10.dp)),
        )
    } else {
        Row(
            modifier = Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Rounded.ContentCopy,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(16.dp),
            )
            androidx.compose.foundation.layout.Spacer(Modifier.width(8.dp))
            Text(
                text = attachment.name,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun AssistantMessage(
    message: Message,
    onFeedback: (Int) -> Unit,
    onRegenerate: () -> Unit,
    modifier: Modifier,
) {
    val clipboard = LocalClipboardManager.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
    ) {
        if (message.content.isBlank() && message.streaming) {
            ThinkingIndicator(modifier = Modifier.padding(top = 6.dp, bottom = 10.dp))
        } else {
            Row(verticalAlignment = Alignment.Bottom) {
                MarkdownMessage(
                    content = message.content,
                    modifier = Modifier.weight(1f),
                )
                if (message.streaming) {
                    StreamingCursor()
                }
            }
        }

        if (message.error != null) {
            Text(
                text = message.error,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(top = 8.dp),
            )
        }

        if (!message.streaming && message.content.isNotBlank()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                MessageAction(
                    icon = Icons.Rounded.ContentCopy,
                    contentDescription = "Copy response",
                    onClick = { clipboard.setText(AnnotatedString(message.content)) },
                )
                MessageAction(
                    icon = Icons.Rounded.ThumbUp,
                    contentDescription = "Good response",
                    active = message.feedback == 1,
                    onClick = { onFeedback(if (message.feedback == 1) 0 else 1) },
                )
                MessageAction(
                    icon = Icons.Rounded.ThumbDown,
                    contentDescription = "Bad response",
                    active = message.feedback == -1,
                    onClick = { onFeedback(if (message.feedback == -1) 0 else -1) },
                )
                MessageAction(
                    icon = Icons.Rounded.Refresh,
                    contentDescription = "Regenerate",
                    onClick = onRegenerate,
                )
            }
        }
    }
}

@Composable
private fun MessageAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    active: Boolean = false,
) {
    NeoIconButton(
        icon = icon,
        contentDescription = contentDescription,
        onClick = onClick,
        tint = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        containerSize = 34.dp,
        iconSize = 17.dp,
    )
}
