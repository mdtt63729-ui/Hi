package com.neogpt.client.util

/**
 * A deliberately small Markdown subset covering what chat responses use:
 * headings, paragraphs, fenced code, ordered/unordered lists, quotes,
 * rules, plus inline bold/italic/code/strikethrough/links.
 *
 * Unknown syntax is preserved as literal text rather than dropped.
 */
sealed interface MarkdownBlock {
    data class Heading(val level: Int, val spans: List<InlineSpan>) : MarkdownBlock
    data class Paragraph(val spans: List<InlineSpan>) : MarkdownBlock
    data class Code(val language: String?, val code: String) : MarkdownBlock
    data class ListBlock(val ordered: Boolean, val items: List<List<InlineSpan>>) : MarkdownBlock
    data class Quote(val spans: List<InlineSpan>) : MarkdownBlock
    data class UiCard(
        val title: String,
        val subtitle: String = "",
        val items: List<String> = emptyList(),
        val actionLabel: String = "",
    ) : MarkdownBlock
    data class UiChart(
        val title: String,
        val values: List<Pair<String, Float>>,
    ) : MarkdownBlock
    data object Divider : MarkdownBlock
}

sealed interface InlineSpan {
    data class Text(val text: String) : InlineSpan
    data class Bold(val children: List<InlineSpan>) : InlineSpan
    data class Italic(val children: List<InlineSpan>) : InlineSpan
    data class Struck(val children: List<InlineSpan>) : InlineSpan
    data class Code(val text: String) : InlineSpan
    data class Link(val text: String, val url: String) : InlineSpan
}

object Markdown {

    fun parse(source: String): List<MarkdownBlock> {
        val lines = source.replace("\r\n", "\n").split('\n')
        val blocks = mutableListOf<MarkdownBlock>()
        val paragraph = StringBuilder()
        val quote = StringBuilder()
        var listOrdered = false
        var listItems = mutableListOf<String>()

        fun flushParagraph() {
            if (paragraph.isNotBlank()) {
                blocks += MarkdownBlock.Paragraph(parseInline(paragraph.toString().trim()))
            }
            paragraph.clear()
        }

        fun flushQuote() {
            if (quote.isNotBlank()) {
                blocks += MarkdownBlock.Quote(parseInline(quote.toString().trim()))
            }
            quote.clear()
        }

        fun flushList() {
            if (listItems.isNotEmpty()) {
                blocks += MarkdownBlock.ListBlock(
                    ordered = listOrdered,
                    items = listItems.map { parseInline(it) },
                )
            }
            listItems = mutableListOf()
        }

        fun flushAll() {
            flushParagraph(); flushQuote(); flushList()
        }

        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            val trimmed = line.trimStart()

            if (trimmed.startsWith("```")) {
                flushAll()
                val language = trimmed.removePrefix("```").trim().ifBlank { null }
                i++
                val code = StringBuilder()
                while (i < lines.size && !lines[i].trimStart().startsWith("```")) {
                    code.appendLine(lines[i])
                    i++
                }
                if (i < lines.size) i++ // closing fence
                blocks += MarkdownBlock.Code(language, code.toString().trimEnd('\n'))
                continue
            }

            when {
                line.isBlank() -> {
                    flushParagraph(); flushQuote(); flushList()
                }

                trimmed.matches(Regex("^#{1,6}\\s+.*")) -> {
                    flushAll()
                    val level = trimmed.takeWhile { it == '#' }.length
                    val text = trimmed.drop(level).trim()
                    blocks += MarkdownBlock.Heading(level, parseInline(text))
                }

                trimmed.matches(Regex("^(-{3,}|\\*{3,}|_{3,})$")) -> {
                    flushAll()
                    blocks += MarkdownBlock.Divider
                }

                trimmed.startsWith("> ") || trimmed == ">" -> {
                    flushParagraph(); flushList()
                    quote.appendLine(trimmed.removePrefix(">").trimStart())
                }

                trimmed.matches(Regex("^([-*+])\\s+.*")) -> {
                    flushParagraph(); flushQuote()
                    if (listItems.isNotEmpty() && listOrdered) flushList()
                    listOrdered = false
                    listItems.add(trimmed.substring(1).trimStart())
                }

                trimmed.matches(Regex("^\\d+[.)]\\s+.*")) -> {
                    flushParagraph(); flushQuote()
                    if (listItems.isNotEmpty() && !listOrdered) flushList()
                    listOrdered = true
                    val item = trimmed.replaceFirst(Regex("^\\d+[.)]\\s+"), "")
                    listItems.add(item)
                }

                else -> {
                    flushQuote(); flushList()
                    if (paragraph.isNotEmpty()) paragraph.append('\n')
                    paragraph.append(line.trim())
                }
            }
            i++
        }
        flushAll()
        return blocks
    }

    private fun parseUiBlock(raw: String): MarkdownBlock? = runCatching {
        val json = org.json.JSONObject(raw)
        when (json.optString("type", "card").lowercase()) {
            "card" -> {
                val itemsJson = json.optJSONArray("items")
                val items = buildList {
                    if (itemsJson != null) for (i in 0 until itemsJson.length()) {
                        val item = itemsJson.optString(i).trim()
                        if (item.isNotEmpty()) add(item)
                    }
                }.take(8)
                val title = json.optString("title").trim()
                if (title.isBlank()) return null
                MarkdownBlock.UiCard(
                    title = title.take(100),
                    subtitle = json.optString("subtitle").take(180),
                    items = items,
                    actionLabel = json.optString("action").take(36),
                )
            }
            "chart" -> {
                val data = json.optJSONArray("values") ?: return null
                val values = buildList {
                    for (i in 0 until minOf(data.length(), 8)) {
                        val point = data.optJSONObject(i) ?: continue
                        val label = point.optString("label").take(32)
                        val value = point.optDouble("value", Double.NaN).toFloat()
                        if (label.isNotBlank() && value.isFinite() && value >= 0f) add(label to value)
                    }
                }
                val title = json.optString("title").trim()
                if (title.isBlank() || values.isEmpty()) return null
                MarkdownBlock.UiChart(title.take(100), values)
            }
            else -> null
        }
    }.getOrNull()

    fun parseInline(text: String): List<InlineSpan> {
        val out = mutableListOf<InlineSpan>()
        val buffer = StringBuilder()

        fun flush() {
            if (buffer.isNotEmpty()) {
                out += InlineSpan.Text(buffer.toString())
                buffer.clear()
            }
        }

        var i = 0
        while (i < text.length) {
            val c = text[i]
            when {
                text.startsWith("**", i) -> {
                    val end = text.indexOf("**", i + 2)
                    if (end > i + 2) {
                        flush()
                        out += InlineSpan.Bold(parseInline(text.substring(i + 2, end)))
                        i = end + 2
                    } else {
                        buffer.append(c); i++
                    }
                }

                text.startsWith("~~", i) -> {
                    val end = text.indexOf("~~", i + 2)
                    if (end > i + 2) {
                        flush()
                        out += InlineSpan.Struck(parseInline(text.substring(i + 2, end)))
                        i = end + 2
                    } else {
                        buffer.append(c); i++
                    }
                }

                c == '`' -> {
                    val end = text.indexOf('`', i + 1)
                    if (end > i + 1) {
                        flush()
                        out += InlineSpan.Code(text.substring(i + 1, end))
                        i = end + 1
                    } else {
                        buffer.append(c); i++
                    }
                }

                (c == '*' || c == '_') && i + 1 < text.length && !text[i + 1].isWhitespace() -> {
                    val end = text.indexOf(c, i + 1)
                    if (end > i + 1) {
                        flush()
                        out += InlineSpan.Italic(parseInline(text.substring(i + 1, end)))
                        i = end + 1
                    } else {
                        buffer.append(c); i++
                    }
                }

                c == '[' -> {
                    val close = text.indexOf(']', i)
                    val open = if (close > i) text.indexOf('(', close) else -1
                    val endParen = if (open == close + 1) text.indexOf(')', open) else -1
                    if (close > i && open == close + 1 && endParen > open) {
                        val label = text.substring(i + 1, close)
                        val url = text.substring(open + 1, endParen).trim()
                        flush()
                        if (url.startsWith("http://") || url.startsWith("https://")) {
                            out += InlineSpan.Link(label, url)
                        } else {
                            out += InlineSpan.Text(label)
                        }
                        i = endParen + 1
                    } else {
                        buffer.append(c); i++
                    }
                }

                else -> {
                    buffer.append(c); i++
                }
            }
        }
        flush()
        return out
    }

    fun plainText(blocks: List<MarkdownBlock>): String = buildString {
        blocks.forEach { block ->
            when (block) {
                is MarkdownBlock.Heading -> appendLine(inlinePlain(block.spans))
                is MarkdownBlock.Paragraph -> appendLine(inlinePlain(block.spans))
                is MarkdownBlock.Quote -> appendLine(inlinePlain(block.spans))
                is MarkdownBlock.Code -> appendLine(block.code)
                is MarkdownBlock.ListBlock -> block.items.forEach { appendLine("• " + inlinePlain(it)) }
                is MarkdownBlock.UiCard -> {
                    appendLine(block.title)
                    if (block.subtitle.isNotBlank()) appendLine(block.subtitle)
                    block.items.forEach { appendLine("• $it") }
                }
                is MarkdownBlock.UiChart -> {
                    appendLine(block.title)
                    block.values.forEach { appendLine("${it.first}: ${it.second}") }
                }
                MarkdownBlock.Divider -> Unit
            }
        }
    }.trim()

    private fun inlinePlain(spans: List<InlineSpan>): String = buildString {
        spans.forEach { span ->
            when (span) {
                is InlineSpan.Text -> append(span.text)
                is InlineSpan.Bold -> append(inlinePlain(span.children))
                is InlineSpan.Italic -> append(inlinePlain(span.children))
                is InlineSpan.Struck -> append(inlinePlain(span.children))
                is InlineSpan.Code -> append(span.text)
                is InlineSpan.Link -> append(span.text)
            }
        }
    }
}
