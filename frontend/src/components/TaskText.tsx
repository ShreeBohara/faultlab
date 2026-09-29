import { describeTaskText, escapedTaskText, TASK_TEXT_MAX_CHARACTERS } from '../taskText'

/**
 * Shows a task instruction faithfully: invisible characters, including every default-ignorable
 * character such as variation selectors (one emoji presentation selector after a visible
 * character excepted), appear as ⟨U+…⟩ markers; long blank padding collapses into one visible
 * marker that counts every hidden character on those lines. Any marked character brings the
 * warning and the escaped copy. The recorded text itself is never changed.
 */
export function TaskText({ text, detailed = false }: { text: string; detailed?: boolean }) {
  const view = describeTaskText(text)
  const plain = view.pieces.length === 1 && view.pieces[0].kind === 'text'
  const body = <span className="task-text">{plain ? text : view.pieces.map((piece, index) => piece.kind === 'text' ? piece.text : <span key={index} className="task-mark" title={piece.title}>{piece.text}</span>)}</span>
  if (!detailed) return body
  const notes = [
    view.invisible ? `${view.invisible} invisible ${view.invisible === 1 ? 'character' : 'characters'}` : '',
    view.collapsedLines ? `${view.collapsedLines} blank lines of padding` : '',
    view.collapsedSpaces ? `a run of ${view.collapsedSpaces} spaces` : '',
  ].filter(Boolean)
  return <>
    {body}
    <span className="task-meta">{view.characters} of {TASK_TEXT_MAX_CHARACTERS} characters, counted as Unicode code points like the backend.</span>
    {notes.length > 0 && <span className="task-warning" role="note">This task contains {notes.join(' and ')}. {view.invisible ? 'Each invisible character is shown as ⟨U+…⟩. ' : ''}{view.collapsedLines || view.collapsedSpaces ? 'Padding is collapsed into one marker. ' : ''}The agent receives the text exactly as recorded.</span>}
    {notes.length > 0 && <details className="task-escaped"><summary>Show every character, escaped</summary><pre>{escapedTaskText(text)}</pre></details>}
  </>
}
