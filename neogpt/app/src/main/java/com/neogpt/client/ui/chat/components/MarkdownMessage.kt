package com.neogpt.client.ui.chat.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.neogpt.client.ui.theme.CodeTextStyle
import com.neogpt.client.ui.theme.NeoTheme
import com.neogpt.client.util.InlineSpan
import com.neogpt.client.util.Markdown
import com.neogpt.client.util.MarkdownBlock

@Composable
fun MarkdownMessage(
    content: String,
    modifier: Modifier = Modifier,
    baseStyle: TextStyle = MaterialTheme.typography.bodyLarge.copy(
        color = NeoTheme.colors.assistantText,
    ),
) {
    val blocks = remember(content) { Markdown.parse(content) }
    SelectionContainer {
        Column(
            modifier = modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            blocks.forEach { block ->
                when (block) {
                    is MarkdownBlock.Heading -> Text(
                        text = inlineAnnotated(block.spans),
                        style = baseStyle.copy(
                            fontSize = when (block.level) {
                                1 -> 24.sp
                                2 -> 20.sp
                                else -> 17.sp
                            },
                            fontWeight = FontWeight.SemiBold,
                            lineHeight = 30.sp,
                        ),
                        modifier = Modifier.padding(top = 4.dp),
                    )

                    is MarkdownBlock.Paragraph -> Text(
                        text = inlineAnnotated(block.spans),
                        style = baseStyle,
                    )

                    is MarkdownBlock.Code -> CodeBlock(
                        language = block.language,
                        code = block.code,
                    )

                    is MarkdownBlock.ListBlock -> Column(
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        block.items.forEachIndexed { index, item ->
                            Row(modifier = Modifier.fillMaxWidth()) {
                                Text(
                                    text = if (block.ordered) "${index + 1}." else "\u2022",
                                    style = baseStyle,
                                    modifier = Modifier.width(22.dp),
                                )
                                Text(text = inlineAnnotated(item), style = baseStyle)
                            }
                        }
                    }

                    is MarkdownBlock.Quote -> Row(
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Box(
                            modifier = Modifier
                                .width(3.dp)
                                .background(NeoTheme.colors.chipBorder, RoundedCornerShape(2.dp))
                                .align(Alignment.CenterVertically)
                                .padding(vertical = 2.dp),
                        ) {
                            Spacer(Modifier.size(width = 3.dp, height = 20.dp))
                        }
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = inlineAnnotated(block.spans),
                            style = baseStyle.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                        )
                    }

                    is MarkdownBlock.UiCard -> GeneratedUiCard(block)
                    is MarkdownBlock.UiChart -> GeneratedUiChart(block)
                    MarkdownBlock.Divider -> HorizontalDivider(color = NeoTheme.colors.divider)
                }
            }
        }
    }
}

@Composable
private fun GeneratedUiCard(block: MarkdownBlock.UiCard) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)),
        border = androidx.compose.foundation.BorderStroke(1.dp, NeoTheme.colors.divider),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(block.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            if (block.subtitle.isNotBlank()) {
                Text(block.subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            block.items.forEach { item ->
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("•", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
                    Text(item, style = MaterialTheme.typography.bodyMedium)
                }
            }
            if (block.actionLabel.isNotBlank()) {
                Text(
                    block.actionLabel,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@Composable
private fun GeneratedUiChart(block: MarkdownBlock.UiChart) {
    val maxValue = (block.values.maxOfOrNull { it.second } ?: 1f).coerceAtLeast(1f)
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)),
        border = androidx.compose.foundation.BorderStroke(1.dp, NeoTheme.colors.divider),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(block.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            block.values.forEach { (label, value) ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                        Text(label, style = MaterialTheme.typography.bodySmall)
                        Text(
                            if (value % 1f == 0f) value.toInt().toString() else "%.1f".format(value),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    androidx.compose.material3.LinearProgressIndicator(
                        progress = { (value / maxValue).coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth().height(7.dp).clip(RoundedCornerShape(8.dp)),
                        color = MaterialTheme.colorScheme.primary,
                        trackColor = NeoTheme.colors.divider,
                    )
                }
            }
        }
    }
}

@Composable
private fun CodeBlock(language: String?, code: String) {
    val clipboard = LocalClipboardManager.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(NeoTheme.colors.codeBackground),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = language ?: "code",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Icon(
                imageVector = Icons.Rounded.ContentCopy,
                contentDescription = "Copy code",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .size(30.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .clickable { clipboard.setText(AnnotatedString(code)) }
                    .padding(6.dp),
            )
        }
        Text(
            text = code,
            style = CodeTextStyle.copy(color = MaterialTheme.colorScheme.onSurface),
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(start = 14.dp, end = 14.dp, top = 4.dp, bottom = 14.dp),
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun inlineAnnotated(spans: List<InlineSpan>): AnnotatedString {
    val linkColor = MaterialTheme.colorScheme.primary
    val codeBackground = NeoTheme.colors.codeBackground
    return buildAnnotatedString { appendInline(spans, linkColor, codeBackground) }
}

private fun androidx.compose.ui.text.AnnotatedString.Builder.appendInline(
    spans: List<InlineSpan>,
    linkColor: androidx.compose.ui.graphics.Color,
    codeBackground: androidx.compose.ui.graphics.Color,
) {
    spans.forEach { span ->
        when (span) {
            is InlineSpan.Text -> append(span.text)
            is InlineSpan.Bold -> {
                pushStyle(SpanStyle(fontWeight = FontWeight.Bold))
                appendInline(span.children, linkColor, codeBackground)
                pop()
            }

            is InlineSpan.Italic -> {
                pushStyle(SpanStyle(fontStyle = androidx.compose.ui.text.font.FontStyle.Italic))
                appendInline(span.children, linkColor, codeBackground)
                pop()
            }

            is InlineSpan.Struck -> {
                pushStyle(SpanStyle(textDecoration = TextDecoration.LineThrough))
                appendInline(span.children, linkColor, codeBackground)
                pop()
            }

            is InlineSpan.Code -> {
                pushStyle(
                    SpanStyle(
                        fontFamily = FontFamily.Monospace,
                        background = codeBackground,
                        fontSize = 14.sp,
                    )
                )
                append(span.text)
                pop()
            }

            is InlineSpan.Link -> withLink(
                LinkAnnotation.Url(
                    url = span.url,
                    styles = TextLinkStyles(style = SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline)),
                )
            ) {
                append(span.text)
            }
        }
    }
}
