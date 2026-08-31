package com.gaskony.scriptide.gateway.lang;

import java.util.ArrayList;
import java.util.List;

/**
 * One open document, and the position arithmetic every LSP feature depends on.
 *
 * <h2>Positions are UTF-16 code units, not characters and not bytes</h2>
 *
 * <p>That is the LSP specification, and it is the detail that silently corrupts an
 * editor integration if you get it wrong. A line containing an emoji or any
 * character outside the Basic Multilingual Plane occupies TWO UTF-16 units per
 * character, so a naive codepoint-based offset drifts and every completion,
 * diagnostic and go-to-definition after it lands in the wrong place. Java's own
 * {@code String} is UTF-16 internally, so counting {@code char}s is correct here
 * — but only because that happens to match, and it is worth knowing why rather
 * than by luck.</p>
 */
public final class TextDocument {

    private final String uri;
    private String text;
    private int version;

    /** Start offset of each line, rebuilt whenever the text changes. */
    private int[] lineStarts;

    public TextDocument(String uri, String text, int version) {
        this.uri = uri;
        this.version = version;
        setText(text);
    }

    public String uri() {
        return uri;
    }

    public String text() {
        return text;
    }

    public int version() {
        return version;
    }

    public void setVersion(int version) {
        this.version = version;
    }

    /** Replace the whole document (LSP full sync). */
    public void setText(String newText) {
        this.text = newText == null ? "" : newText;
        this.lineStarts = computeLineStarts(this.text);
    }

    /**
     * Apply one incremental change.
     *
     * <p>Ranges are half-open: the end position is exclusive. Applying them in the
     * order the client sent them matters — each is expressed against the document
     * as it stood after the previous one.</p>
     */
    public void applyChange(int startLine, int startChar, int endLine, int endChar,
                            String replacement) {
        int start = offsetOf(startLine, startChar);
        int end = offsetOf(endLine, endChar);
        if (end < start) {
            int swap = start;
            start = end;
            end = swap;
        }
        setText(text.substring(0, start) + replacement + text.substring(end));
    }

    /** Zero-based line count. A document always has at least one line. */
    public int lineCount() {
        return lineStarts.length;
    }

    /**
     * Character offset of a (line, character) position, clamped into the document.
     *
     * <p>Clamped rather than throwing: a client's position can legitimately lag the
     * document by a keystroke, and answering a slightly stale request at the
     * nearest valid spot is far better than failing the whole request.</p>
     */
    public int offsetOf(int line, int character) {
        if (line < 0) {
            return 0;
        }
        if (line >= lineStarts.length) {
            return text.length();
        }
        int lineStart = lineStarts[line];
        int lineEnd = (line + 1 < lineStarts.length) ? lineStarts[line + 1] : text.length();
        // Do not run past the newline into the next line.
        int maxChar = Math.max(0, lineEnd - lineStart);
        return lineStart + Math.min(Math.max(0, character), maxChar);
    }

    /** The text of one line, without its terminator. */
    public String lineText(int line) {
        if (line < 0 || line >= lineStarts.length) {
            return "";
        }
        int start = lineStarts[line];
        int end = (line + 1 < lineStarts.length) ? lineStarts[line + 1] : text.length();
        String raw = text.substring(start, end);
        return raw.endsWith("\n") ? raw.substring(0, raw.length() - 1) : raw;
    }

    /**
     * The dotted expression immediately before a position, e.g. {@code system.tag.re}
     * for a cursor just after {@code re}.
     *
     * <p>Deliberately lexical rather than parsed: a completion is requested while the
     * document is, by definition, half-written and usually not parseable at all.
     * Walking back over identifier characters and dots is what actually works at a
     * cursor. It stops at anything that cannot be part of a dotted name, so a call
     * argument or a string literal does not bleed into the prefix.</p>
     */
    public String dottedPrefixAt(int line, int character) {
        String lineContent = lineText(line);
        int end = Math.min(Math.max(0, character), lineContent.length());
        int start = end;
        while (start > 0) {
            char c = lineContent.charAt(start - 1);
            if (Character.isLetterOrDigit(c) || c == '_' || c == '.') {
                start--;
            } else {
                break;
            }
        }
        return lineContent.substring(start, end);
    }

    private static int[] computeLineStarts(String text) {
        List<Integer> starts = new ArrayList<>();
        starts.add(0);
        for (int i = 0; i < text.length(); i++) {
            if (text.charAt(i) == '\n') {
                starts.add(i + 1);
            }
        }
        int[] out = new int[starts.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = starts.get(i);
        }
        return out;
    }
}
