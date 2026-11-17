// AI answers use a little Markdown: "* " bullet lines and **bold**. Show
// those properly, and turn [1] into a button that opens that save.
type Links = { byNumber: Map<number, number>; onOpen: (id: number) => void };

export default function AnswerText({ text, byNumber, onOpen }: { text: string } & Links) {
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  const blocks: { bullet: boolean; lines: string[] }[] = [];
  for (const line of lines) {
    const bullet = /^\s*[*-]\s+/.test(line);
    const clean = line.replace(/^\s*[*-]\s+/, "");
    const last = blocks[blocks.length - 1];
    if (last && last.bullet === bullet && bullet) last.lines.push(clean);
    else blocks.push({ bullet, lines: [clean] });
  }
  return (
    <>
      {blocks.map((block, index) =>
        block.bullet ? (
          <ul key={index} className="list-disc space-y-1 pl-5">
            {block.lines.map((line, i) => (
              <li key={i}>
                <Inline text={line} byNumber={byNumber} onOpen={onOpen} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={index}>
            <Inline text={block.lines[0]} byNumber={byNumber} onOpen={onOpen} />
          </p>
        ),
      )}
    </>
  );
}

function Inline({ text, byNumber, onOpen }: { text: string } & Links) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*|\[\d+\])/).map((piece, index) => {
        if (/^\*\*[^*]+\*\*$/.test(piece)) return <strong key={index}>{piece.slice(2, -2)}</strong>;
        const number = /^\[(\d+)\]$/.exec(piece)?.[1];
        if (!number) return piece ? <span key={index}>{piece}</span> : null;
        const itemId = byNumber.get(Number(number));
        if (itemId === undefined) return null; // a number that isn't one of the saves
        return (
          <button
            key={index}
            type="button"
            onClick={() => onOpen(itemId)}
            className="mx-0.5 rounded bg-indigo-100 px-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900/60 dark:text-indigo-200"
            aria-label={`Open save ${number}`}
          >
            {number}
          </button>
        );
      })}
    </>
  );
}
