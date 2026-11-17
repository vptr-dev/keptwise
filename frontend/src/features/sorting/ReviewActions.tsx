// The choices under a save in Needs review: why the AI wasn't sure, and one
// click to put it where it suggested (or to make the collection it proposed).
import { Button } from "../../components/ui";
import type { ItemCard as Item } from "./sortingApi";

export default function ReviewActions({
  item,
  room,
  onAccept,
}: {
  item: Item;
  room: boolean;
  onAccept: (choice: { collection_id?: number; new_name?: string }) => void;
}) {
  const best = item.suggestions[0];
  return (
    <div className="rounded-xl bg-amber-50 px-3 py-2.5 text-sm dark:bg-amber-950/40">
      <p className="text-amber-900 dark:text-amber-200">{item.review_reason ?? "The AI wasn't sure."}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {best && (
          <Button size="sm" onClick={() => onAccept({ new_name: best.name })}>
            Put in {best.name}
          </Button>
        )}
        {item.new_collection && room && (
          <Button size="sm" variant="secondary" onClick={() => onAccept({ new_name: item.new_collection ?? undefined })}>
            Make “{item.new_collection}”
          </Button>
        )}
        <span className="self-center text-xs text-amber-800/80 dark:text-amber-200/70">or use “Move to…” above.</span>
      </div>
    </div>
  );
}
