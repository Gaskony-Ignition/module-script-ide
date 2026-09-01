/**
 * The CodeMirror pieces shared by every editing surface in this app.
 *
 * Extracted when the Script Console arrived: the console is a Python editor too,
 * and giving it its own theme and its own indent rules would have meant a tab
 * typed in the console and a tab typed in a file eventually disagreeing about
 * what a tab is. The byte-fidelity facets in particular are a property of
 * "editing Jython here", not of any one component.
 *
 * Nothing in this file knows about documents, tabs, saving or the language
 * server. Those belong to the component that composes them.
 */
import { indentUnit, syntaxHighlighting, HighlightStyle, bracketMatching } from '@codemirror/language';
import { python } from '@codemirror/lang-python';
import { EditorState, type Extension } from '@codemirror/state';
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  drawSelection,
  rectangularSelection,
  highlightSpecialChars,
} from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentLess, insertTab } from '@codemirror/commands';
import { highlightSelectionMatches, search, searchKeymap } from '@codemirror/search';
import { tags } from '@lezer/highlight';

/**
 * Syntax colours, expressed with the design tokens rather than CodeMirror's own
 * defaults — those are tuned for a light page and are barely legible here.
 */
export const highlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: 'var(--syntax-keyword)' },
  { tag: [tags.controlKeyword, tags.moduleKeyword], color: 'var(--syntax-keyword)' },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName], color: 'var(--text-primary)' },
  { tag: [tags.function(tags.variableName), tags.labelName], color: 'var(--syntax-function)' },
  { tag: [tags.definition(tags.variableName)], color: 'var(--text-primary)' },
  { tag: [tags.className, tags.typeName], color: 'var(--syntax-type)' },
  { tag: [tags.number, tags.bool, tags.null], color: 'var(--syntax-number)' },
  { tag: [tags.string, tags.special(tags.string)], color: 'var(--syntax-string)' },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: 'var(--syntax-comment)', fontStyle: 'italic' },
  { tag: [tags.operator, tags.punctuation], color: 'var(--text-secondary)' },
  { tag: tags.invalid, color: 'var(--error)' },
]);

export const editorTheme = EditorView.theme(
  {
    '&': {
      height: '100%',
      backgroundColor: 'var(--bg-primary)',
      color: 'var(--text-primary)',
      fontSize: 'var(--font-size-code)',
    },
    '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.4' },
    '.cm-content': { caretColor: 'var(--accent-primary)' },
    '.cm-gutters': {
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-muted)',
      border: 'none',
      borderRight: '1px solid var(--border-light)',
    },
    '.cm-activeLine': { backgroundColor: 'var(--bg-tertiary)' },
    '.cm-activeLineGutter': { backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' },
    '&.cm-focused .cm-cursor': { borderLeftColor: 'var(--accent-primary)' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': {
      backgroundColor: 'var(--accent-primary-bg)',
    },
    '.cm-matchingBracket, &.cm-focused .cm-matchingBracket': {
      backgroundColor: 'var(--accent-primary-bg)',
      color: 'inherit',
    },
  },
  { dark: true }
);

/**
 * Facets that make this editor write the bytes the Designer writes.
 *
 * Kept as their own export, and applied LAST by every composer, because a
 * language extension that set its own `indentUnit` would otherwise win a
 * precedence tie and start emitting spaces. See CodeEditor's class comment.
 */
export const byteFidelity: Extension[] = [
  // A literal tab, so every indent CodeMirror generates (auto-indent after a
  // ':', indentMore, indentOnInput) is a tab and never spaces.
  indentUnit.of('\t'),
  // Tab width for DISPLAY and for the column arithmetic the Python indenter
  // does; it never converts a tab into spaces.
  EditorState.tabSize.of(4),
  // Pin the line separator. Left at its default, CodeMirror splits the document
  // on any of CR, LF or CRLF and rejoins with \n — so opening and saving a file
  // with CRLF endings rewrites every line, invisibly.
  EditorState.lineSeparator.of('\n'),
];

/**
 * Find and replace: Ctrl+F, Ctrl+H, F3, and match highlighting.
 *
 * CodeMirror's own panel rather than a hand-rolled one — it already handles
 * regex, case sensitivity, whole-word, replace-all and the wrap-around, and each
 * of those is a small bug waiting to happen if reimplemented.
 *
 * `top: true` puts the panel above the editor, where VS Code's is; the default
 * is the bottom, which on this layout collides with the console pane.
 */
export const findAndReplace: Extension[] = [
  search({ top: true }),
  highlightSelectionMatches(),
  keymap.of(searchKeymap),
];

/** Editing surface, syntax and history — everything but keymaps and fidelity. */
export const pythonSurface: Extension[] = [
  lineNumbers(),
  highlightActiveLineGutter(),
  highlightSpecialChars(),
  history(),
  drawSelection(),
  rectangularSelection(),
  highlightActiveLine(),
  bracketMatching(),
  syntaxHighlighting(highlightStyle, { fallback: true }),
  python(),
];

/**
 * The default keymap, with Tab bound to a literal tab.
 *
 * `insertTab` inserts the `indentUnit`, which the facet above pins to a tab, so
 * this binding is what connects the fidelity rule to the keyboard.
 */
export const pythonKeymap: Extension = keymap.of([
  { key: 'Tab', run: insertTab, shift: indentLess },
  ...defaultKeymap,
  ...historyKeymap,
]);
