import { icons } from "../../components/icons";

type Chapter = {
  id: string;
  name: string;
  title: string;
  intro: string;
  icon: keyof typeof icons;
  steps: [string, string][];
  preview: { title: string; rows: [string, string][] };
  destination: [label: string, path: string];
};

export const CHAPTERS: Chapter[] = [
  {
    id: "start", name: "Start here", title: "Find your way around Keptwise",
    intro: "Bring in a few saved videos, make one of them easy to find, then turn it into something you can use.",
    icon: "library",
    steps: [
      ["Start in Import", "Bring in a data export from TikTok, YouTube, Instagram or Facebook. Your saves appear in Library."],
      ["Make it easy to find", "File a save yourself in Collections or use Sort to get transcripts, notes and suggestions."],
      ["Find anything from the sidebar", "Use the platform picker at the top to switch between All and one platform. Press Ctrl+K to search for a save or jump to a page."],
    ],
    preview: { title: "A typical first visit", rows: [["Import", "Bring in your export"], ["Library", "Explore your saves"], ["Sort", "Add searchable notes"]] },
    destination: ["Open Library", "/library"],
  },
  {
    id: "import", name: "Import", title: "Bring in your first export",
    intro: "Keptwise reads the files the platform gives you. You can import again as your saved list grows.",
    icon: "import",
    steps: [
      ["Request your data", "Open Import and expand the guide for your platform. Choose JSON where the platform offers it. YouTube uses a Google Takeout export of playlists."],
      ["Drop in the file", "Drag the downloaded ZIP onto Import or use Choose zip file. You can also choose the extracted folder. The result shows what was new and what was already here."],
      ["Choose where new saves go", "Set a default collection for a platform or link a known source playlist. The supported TikTok export gives collection names without saying which videos belong to them."],
    ],
    preview: { title: "Import receipt", rows: [["TikTok export", "Import finished"], ["New saves", "12"], ["Already in Library", "3"]] },
    destination: ["Open Import", "/import"],
  },
  {
    id: "library", name: "Library", title: "Browse, filter and open a save",
    intro: "Library is the starting point when you remember a platform, creator or topic.",
    icon: "library",
    steps: [
      ["Narrow the list", "Pick a platform, then use the filters for collections, tags, creator and progress. To see new saves that still need a home, choose In no collection."],
      ["Open a card", "Read its caption, transcript and any notes. Use Open original when you want to watch it on the platform."],
      ["Work on several saves", "Click Select, pick the cards you want and use the selection bar to file, tag or archive them together. Right-click a single card for its actions."],
    ],
    preview: { title: "Library filters", rows: [["Platform", "TikTok"], ["Collection", "In no collection"], ["Creator", "Any creator"]] },
    destination: ["Open Library", "/library"],
  },
  {
    id: "organise", name: "Collections & tags", title: "Give saves a place and a label",
    intro: "Collections group saves you want to browse together. Tags connect details across collections.",
    icon: "folder",
    steps: [
      ["Make a home for related saves", "In Collections, create a folder like Weeknight meals. Spaces can keep groups such as Personal and Work apart. Drag folders to organise the tree."],
      ["File a save", "Use the save’s collection action to add it to a folder. Inside Collections, you can also drag saves onto a folder. A save can belong to more than one collection."],
      ["Use tags for details", "Add tags such as 20 minutes or meal prep. Use the Tags page to browse them and the Library filters to combine them with a collection."],
    ],
    preview: { title: "One save, several ways to find it", rows: [["Collection", "Weeknight meals"], ["Tag", "20 minutes"], ["Tag", "Meal prep"]] },
    destination: ["Open Collections", "/collections"],
  },
  {
    id: "sort", name: "Sort & notes", title: "Turn saves into searchable notes",
    intro: "Try a small batch first. You can review the results before putting more of the library through AI.",
    icon: "transcripts",
    steps: [
      ["Get transcripts", "On Sort, choose a small batch under Get transcripts. Keptwise reads public video pages and transcribes speech on this PC."],
      ["Write notes", "Use Write the notes for titles, summaries and steps. Set up a provider in Settings → AI first. Keptwise asks before starting a paid cloud batch."],
      ["Review the suggestions", "In Unsorted, accept the suggested collection or choose one yourself. Review suggested tags too. Turn on automatic filing or tagging in Settings → Workflow when you want it."],
    ],
    preview: { title: "What one save goes through", rows: [["Get transcripts", "Speech turned into text"], ["Write the notes", "Summary and steps"], ["Review", "Accept or choose a folder"]] },
    destination: ["Open Sort", "/transcripts"],
  },
  {
    id: "search", name: "Search & Assistant", title: "Find what a video said",
    intro: "Search your captions, transcripts and notes, or ask the Assistant to pull together several saves.",
    icon: "search",
    steps: [
      ["Search for something you remember", "Press Ctrl+K, type a phrase such as quick pasta and open the search results. Read the matching snippet and open the save to see it in context."],
      ["Try similar ideas", "Use Similar ideas to look for related meaning when you can’t remember the exact words. Search can use your captions and transcripts before AI notes are ready."],
      ["Ask a question about your library", "In AI Assistant, ask something specific, such as Which recipes take under 20 minutes? Open the cited saves to check where the answer came from."],
    ],
    preview: { title: "Example query", rows: [["Search", "quick pasta"], ["Matched transcript", "Ready in about 15 minutes"], ["Source", "Open the original save"]] },
    destination: ["Try Search", "/search"],
  },
  {
    id: "plans", name: "Plans", title: "Put a save to work",
    intro: "Use Plans for a trip, meal plan, course or any project you want to follow through on.",
    icon: "plans",
    steps: [
      ["Make a plan", "Open Plans and create one, such as Dinners this week. Add the saves you want to use."],
      ["Give it structure", "Group the saves into sections, add a due date, and write your own to-dos beside them."],
      ["Check off what you finish", "Check off each save or task as you go. You can revisit the original save or its notes from the plan."],
    ],
    preview: { title: "Dinners this week", rows: [["Monday", "Lemon pasta"], ["Wednesday", "Vegetable curry"], ["To-do", "Pick up ingredients"]] },
    destination: ["Open Plans", "/plans"],
  },
  {
    id: "archive", name: "Archive & Unsave", title: "Know what happens when you remove a save",
    intro: "Keptwise’s Archive and the platform’s own saved list are separate. You control both.",
    icon: "archive",
    steps: [
      ["Recover a save from Archive", "Archiving moves a save within Keptwise. In Archive → Archived, put it back in Library or choose Delete for good."],
      ["Unsave on the platform yourself", "Unsave is a checklist. Open the original, unsave it on the platform if you want, then mark the step done. Keptwise keeps its local copy."],
      ["Review before clearing the library", "Settings → Storage separates library clearing from clearing backups. A whole-library clear requires you to type DELETE and removes its Undo history."],
    ],
    preview: { title: "Pick the action you need", rows: [["Archive", "Put a save back or delete it for good"], ["Unsave", "Keep the local copy"], ["Storage", "Manage data and backups"]] },
    destination: ["Open Archive", "/archive"],
  },
  {
    id: "settings", name: "Make it yours", title: "Keep the parts that work for you",
    intro: "Start with one import and one collection. Add automation after you’ve seen what it does to your saves.",
    icon: "settings",
    steps: [
      ["Choose your level of automation", "Settings → Workflow controls automatic filing, automatic tagging and local follow-up notes independently."],
      ["Change how the app feels", "In Settings → Appearance, choose a theme, text size, start page and sidebar arrangement. Use the Settings search if you can’t find a control."],
      ["Come back whenever you need help", "Open Settings → Getting started to replay this tutorial, or search for Guided tutorial with Ctrl+K."],
    ],
    preview: { title: "Your first session", rows: [["1", "Import an export"], ["2", "File a save you want to find again"], ["3", "Try notes on a small batch"]] },
    destination: ["Open Workflow settings", "/settings?section=workflow"],
  },
];
