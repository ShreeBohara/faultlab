/**
 * The task-instruction rule shared with the backend (backend/app/contracts/task_text.py).
 *
 * Length is counted in Unicode code points, as the backend counts it: Array.from(text).length,
 * not text.length (UTF-16 units, which count an emoji as two). A task needs at least one
 * visible character: a letter, digit, punctuation mark, symbol or spacing combining mark.
 * Whitespace, line breaks, control and format characters (zero-width characters, the byte-order
 * mark, bidirectional controls), unassigned code points, lone surrogates and letters that render
 * as blank space do not count. The text is never trimmed or rewritten for display or dispatch.
 */
export const TASK_TEXT_MAX_CHARACTERS = 2000
const VISIBLE = /^[\p{L}\p{N}\p{P}\p{S}\p{Mc}]$/u
const COMBINING = /^[\p{Mn}\p{Me}]$/u
/** Assigned characters that render as empty space: the Hangul fillers and the blank Braille pattern. */
const BLANK_RENDERING = new Set(['ᅟ', 'ᅠ', 'ㅤ', 'ﾠ', '⠀'])

export const taskCharacters = (text: string) => Array.from(text).length
export const visibleCharacter = (character: string) => VISIBLE.test(character) && !BLANK_RENDERING.has(character)

/** Why the text cannot be sent to an agent as a task instruction, or null. Mirrors task_text_problem. */
export function taskTextProblem(text: unknown): string | null {
  if (typeof text !== 'string' || !text.length) return 'The task instruction is empty.'
  const characters = Array.from(text)
  if (characters.length > TASK_TEXT_MAX_CHARACTERS) return `The task instruction has ${characters.length} characters; at most ${TASK_TEXT_MAX_CHARACTERS} are allowed.`
  if (!characters.some(visibleCharacter)) return 'The task instruction has no visible character: it contains only spaces, line breaks, zero-width or other invisible characters.'
  return null
}

const NAMES: Record<string, string> = {
  ' ': 'no-break space', '­': 'soft hyphen', '͏': 'combining grapheme joiner', '؜': 'Arabic letter mark', '᠎': 'Mongolian vowel separator',
  '​': 'zero-width space', '‌': 'zero-width non-joiner', '‍': 'zero-width joiner', '‎': 'left-to-right mark', '‏': 'right-to-left mark',
  ' ': 'line separator', ' ': 'paragraph separator', '‪': 'left-to-right embedding', '‫': 'right-to-left embedding', '‬': 'pop directional formatting',
  '‭': 'left-to-right override', '‮': 'right-to-left override', '⁠': 'word joiner', '⁦': 'left-to-right isolate', '⁧': 'right-to-left isolate',
  '⁨': 'first strong isolate', '⁩': 'pop directional isolate', '　': 'ideographic space', 'ㅤ': 'Hangul filler', '﻿': 'byte-order mark (zero-width no-break space)',
  '\r': 'carriage return', '⠀': 'blank Braille pattern',
}
const codePoint = (character: string) => `U+${character.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`
/**
 * Characters that software is expected not to draw: zero-width and format characters, variation
 * selectors (U+FE00–FE0F, U+E0100–E01EF), the combining grapheme joiner (U+034F), tag characters
 * and the like. A string of them can carry a whole hidden sentence behind one visible word.
 */
const DEFAULT_IGNORABLE = /^\p{Default_Ignorable_Code_Point}$/u
/** Text/emoji presentation selectors: one directly after a visible character is ordinary (for example ❤️). */
const PRESENTATION_SELECTORS = new Set(['\uFE0E', '\uFE0F'])

/**
 * For each character of one line: is it shown as a ⟨U+…⟩ marker?
 *
 * Marked: every default-ignorable character, except a single U+FE0E/U+FE0F directly after a
 * visible character; every other character that is not visible, not an ordinary space or tab,
 * and not a combining mark drawn on a visible base. A combining mark with no visible base
 * before it on its line (for example on a blank line) is marked too, so it cannot vanish.
 */
export function markedCharacters(characters: string[]): boolean[] {
  const marks: boolean[] = []; let base = false
  characters.forEach((character, at) => {
    let mark: boolean
    if (character === ' ' || character === '\t' || character === '\n') { mark = false; base = false }
    else if (DEFAULT_IGNORABLE.test(character)) {
      mark = !(PRESENTATION_SELECTORS.has(character) && at > 0 && visibleCharacter(characters[at - 1]))
      if (mark) base = false
    }
    else if (visibleCharacter(character)) { mark = false; base = true }
    else if (COMBINING.test(character)) mark = !base
    else { mark = true; base = false }
    marks.push(mark)
  })
  return marks
}
const markedCount = (line: string) => markedCharacters(Array.from(line)).filter(Boolean).length

export type TaskPiece = { kind: 'text'; text: string } | { kind: 'mark'; text: string; title: string }
export type TaskView = { pieces: TaskPiece[]; characters: number; invisible: number; collapsedLines: number; collapsedSpaces: number }
/** Three or more consecutive blank lines collapse into one marker; one or two are ordinary paragraph spacing. */
export const BLANK_LINE_RUN = 3
/** Sixteen or more consecutive spaces/tabs inside a line collapse into one marker. */
export const SPACE_RUN = 16

/** A faithful display plan: every character is shown, marked by code point, or counted in a collapse marker. */
export function describeTaskText(text: string): TaskView {
  const pieces: TaskPiece[] = []; let invisible = 0; let collapsedLines = 0; let collapsedSpaces = 0
  const push = (piece: TaskPiece) => { const last = pieces[pieces.length - 1]; if (piece.kind === 'text' && last?.kind === 'text') last.text += piece.text; else pieces.push(piece) }
  function renderLine(line: string) {
    const characters = Array.from(line)
    const marks = markedCharacters(characters)
    for (let at = 0; at < characters.length;) {
      const character = characters[at]
      if (character === ' ' || character === '\t') {
        let end = at; while (end < characters.length && (characters[end] === ' ' || characters[end] === '\t')) end++
        if (end - at >= SPACE_RUN) {
          collapsedSpaces += end - at
          push({ kind: 'mark', text: `⟨${end - at} spaces${characters.slice(at, end).includes('\t') ? ' and tabs' : ''}⟩`, title: 'A long run of spaces is collapsed here; it is sent to the agent exactly as recorded.' })
        } else push({ kind: 'text', text: characters.slice(at, end).join('') })
        at = end; continue
      }
      if (marks[at]) {
        invisible++
        push({ kind: 'mark', text: `⟨${codePoint(character)}⟩`, title: `${characterName(character)} (${codePoint(character)}), sent to the agent as recorded` })
      } else push({ kind: 'text', text: character })
      at++
    }
  }
  const lines = text.split('\n')
  const blank = lines.map(line => !Array.from(line).some(visibleCharacter))
  for (let index = 0; index < lines.length;) {
    if (index > 0) push({ kind: 'text', text: '\n' })
    if (blank[index]) {
      let end = index; while (end < lines.length && blank[end]) end++
      if (end - index >= BLANK_LINE_RUN) {
        // One marker stands for the whole run of blank lines and the line breaks between them.
        // Every character on those lines other than a space or tab is marked (a blank line has no
        // visible base), so each one is counted here and in the warning; none can vanish.
        const run = end - index
        const hidden = lines.slice(index, end).reduce((sum, line) => sum + markedCount(line), 0)
        invisible += hidden; collapsedLines += run
        push({ kind: 'mark', text: `⟨${run} blank lines${hidden ? `, ${hidden} invisible ${hidden === 1 ? 'character' : 'characters'}` : ''}⟩`, title: `${run} consecutive lines with no visible character are collapsed here${hidden ? `, with ${hidden} invisible or unattached ${hidden === 1 ? 'character' : 'characters'}; see the escaped copy` : ''}; they are sent to the agent exactly as recorded.` })
        index = end; continue
      }
    }
    renderLine(lines[index]); index++
  }
  return { pieces, characters: taskCharacters(text), invisible, collapsedLines, collapsedSpaces }
}

/**
 * An unambiguous escaped copy. Escaped: line breaks, tabs, backslashes, every marked character
 * and every default-ignorable character (including an allowed emoji presentation selector).
 * Kept as written: spaces, visible characters and combining marks drawn on a visible base.
 */
export function escapedTaskText(text: string): string {
  const lines = text.split('\n').map(line => { const characters = Array.from(line); return { characters, marks: markedCharacters(characters) } })
  return lines.map(({ characters, marks }) => characters.map((character, at) => character === '\t' ? '\\t' : character === '\\' ? '\\\\'
    : !marks[at] && !DEFAULT_IGNORABLE.test(character) ? character
      : character.length > 1 ? `\\u{${character.codePointAt(0)!.toString(16).toUpperCase()}}` : `\\u${character.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')}`).join('')).join('\\n')
}

function characterName(character: string) {
  if (NAMES[character]) return NAMES[character]
  const value = character.codePointAt(0)!
  if ((value >= 0xFE00 && value <= 0xFE0F) || (value >= 0xE0100 && value <= 0xE01EF)) return 'variation selector'
  if (value >= 0xE0000 && value <= 0xE007F) return 'tag character'
  if (COMBINING.test(character)) return DEFAULT_IGNORABLE.test(character) ? 'invisible combining character' : 'combining mark with no visible base'
  return DEFAULT_IGNORABLE.test(character) ? 'default-ignorable (normally invisible) character' : 'invisible or format character'
}
