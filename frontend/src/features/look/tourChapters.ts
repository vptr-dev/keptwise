export const CHAPTERS = [
  {
    id: "import",
    title: "Bring in your first export",
    intro: "Get a ZIP of your saved videos from the platform. Drop it into Import and Keptwise will add any new saves.",
    destination: ["Open Import", "/import"],
  },
  {
    id: "sort",
    title: "Try sorting a save",
    intro: "Use a sample video to try each step. The practice stays here and uses no AI requests.",
    destination: ["Open Sort", "/transcripts"],
  },
  {
    id: "search",
    title: "Find a save again",
    intro: "Search captions, transcripts and notes. Try a word from the practice saves below.",
    destination: ["Open Search", "/search"],
  },
] as const;
