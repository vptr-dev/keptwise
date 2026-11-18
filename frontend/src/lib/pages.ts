// The pages the sidebar can show, in its two sections and the standard
// order (labels only; the icons live in App.tsx). Used by Settings ->
// Appearance to show, hide and reorder them.
export const PAGE_SECTIONS: { id: string; title: string; pages: { path: string; label: string }[] }[] = [
  {
    id: "organise",
    title: "Organise",
    pages: [
      { path: "/library", label: "Library" },
      { path: "/collections", label: "Collections" },
      { path: "/tags", label: "Tags" },
      { path: "/plans", label: "Plans" },
      { path: "/chat", label: "AI Assistant" },
      { path: "/unsave", label: "Unsave" },
      { path: "/archive", label: "Archive" },
    ],
  },
  {
    id: "manage",
    title: "Manage",
    pages: [
      { path: "/import", label: "Import" },
      { path: "/transcripts", label: "Sort" },
      { path: "/settings", label: "Settings" },
    ],
  },
];

export const PAGES = PAGE_SECTIONS.flatMap((section) => section.pages);
