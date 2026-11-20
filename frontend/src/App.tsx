// The whole app: sidebar layout, the platform picker, the first-run wizard,
// the theme, the keyboard shortcuts, the live status corner, and which page
// to show for the address (#/library, ...).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Layout, { type LiveStatus, type NavItem, type NavSection } from "./components/Layout";
import PlatformPicker from "./components/PlatformPicker";
import ShortcutsDialog from "./components/ShortcutsDialog";
import Toasts from "./components/Toasts";
import { icons } from "./components/icons";
import { aiApi, useAiOverview } from "./features/ai/aiApi";
import SetupWizard from "./features/ai/SetupWizard";
import Welcome from "./features/look/Welcome";
import GuidedTour from "./features/look/GuidedTour";
import { libraryApi, type OverviewCounts } from "./features/library/libraryApi";
import { onOrganizeChange } from "./features/organize/organizeApi";
import { arrangeNav } from "./features/organize/tree";
import CommandPalette, { type CommandAction } from "./features/command/CommandPalette";
import UpdateNow from "./features/updates/UpdateNow";
import UndoButtons, { onUndo } from "./features/undo/UndoButtons";
import { updatesApi, type UpdateStatus } from "./features/updates/updatesApi";
import { api } from "./lib/api";
import { navigate, useRoute } from "./lib/router";
import { useScope } from "./lib/scope";
import { applyTheme, nextTheme, revealTheme, useLook, type ThemeChoice } from "./lib/theme";
import { TipsProvider } from "./lib/tips";
import ArchivePage from "./pages/ArchivePage";
import AssistantPage from "./pages/AssistantPage";
import CollectionsPage from "./pages/CollectionsPage";
import DevPage from "./pages/DevPage";
import ImportPage from "./pages/ImportPage";
import ItemPage from "./pages/ItemPage";
import LibraryPage from "./pages/LibraryPage";
import PlanPage from "./pages/PlanPage";
import PlansPage from "./pages/PlansPage";
import SearchPage from "./pages/SearchPage";
import SettingsPage from "./pages/SettingsPage";
import TagsPage from "./pages/TagsPage";
import TranscriptsPage from "./pages/TranscriptsPage";
import UnsavePage from "./pages/UnsavePage";

// How often the sidebar corner checks the backend and the AI.
const BACKEND_EVERY_MS = 15_000;
const AI_EVERY_MS = 30_000;

// The pages, in two sections. The user can drag pages into another order
// within a section and hide some (Settings -> Appearance); Alt+1 to Alt+9
// follow what the sidebar shows.
function buildSections(counts: OverviewCounts | null): { id: string; title: string; items: NavItem[] }[] {
  return [
    {
      id: "organise",
      title: "Organise",
      items: [
        { path: "/library", label: "Library", icon: icons.library },
        { path: "/collections", label: "Collections", icon: icons.folder, badge: counts?.review },
        { path: "/tags", label: "Tags", icon: icons.tag },
        { path: "/plans", label: "Plans", icon: icons.plans, badge: counts?.open_plans },
        { path: "/chat", label: "AI Assistant", icon: icons.sparkle },
        { path: "/unsave", label: "Unsave", icon: icons.unsave, badge: counts?.to_unsave },
        { path: "/archive", label: "Archive", icon: icons.archive },
      ],
    },
    {
      id: "manage",
      title: "Manage",
      items: [
        { path: "/import", label: "Import", icon: icons.import },
        { path: "/transcripts", label: "Sort", icon: icons.transcripts },
        { path: "/settings", label: "Settings", icon: icons.settings },
      ],
    },
  ];
}

function typing(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return !!element && (element.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName));
}

export default function App() {
  const [narrowWindow, setNarrowWindow] = useState(() => window.innerWidth < 840);
  useEffect(() => {
    const resize = () => setNarrowWindow(window.innerWidth < 840);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  const route = useRoute();
  const { overview, setOverview, reload: reloadAi } = useAiOverview();
  const { look, loaded: lookLoaded, changeLook } = useLook();
  const { scope, choose: chooseScope, reload: reloadScope } = useScope();
  const [connected, setConnected] = useState(true);
  const [aiReady, setAiReady] = useState<{ ready: boolean | null; message: string | null }>({ ready: null, message: null });
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [wizardClosed, setWizardClosed] = useState(false);
  const [tutorialRequested, setTutorialRequested] = useState(false);
  const welcome = lookLoaded && look.welcomed === false;
  const showWizard = lookLoaded && !welcome && overview !== null && !overview.setup_done && !wizardClosed;
  const showTutorial = lookLoaded && !welcome && !showWizard &&
    (tutorialRequested || (overview !== null && look.tutorial_seen === false));
  const openTutorial = useCallback(() => setTutorialRequested(true), []);
  const closeTutorial = (destination?: string) => {
    setTutorialRequested(false);
    if (!look.tutorial_seen) changeLook({ tutorial_seen: true });
    if (destination) navigate(destination);
  };
  const [counts, setCounts] = useState<OverviewCounts | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  // Bumped after Undo or Redo, so the page on screen loads its data again.
  const [dataVersion, setDataVersion] = useState(0);
  useEffect(() => onUndo(() => setDataVersion((v) => v + 1)), []);
  const [updates, setUpdates] = useState<UpdateStatus | null>(null);

  // Live status: is the backend there? (every 15 s, and when the window comes back into view)
  useEffect(() => {
    let stopped = false;
    const check = () =>
      api
        .get<{ message: string; version: string }>("/api/hello")
        .then(() => !stopped && setConnected(true))
        .catch(() => !stopped && setConnected(false))
        .finally(() => !stopped && setCheckedAt(new Date()));
    void check();
    const timer = window.setInterval(check, BACKEND_EVERY_MS);
    const onFocus = () => void check();
    window.addEventListener("focus", onFocus);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  // Is the chosen AI ready (Ollama running, the model there, a key saved)? Every 30 s,
  // and straight after the AI is changed in Settings.
  const aiKey = `${overview?.current ?? ""}|${overview?.current_label ?? ""}`;
  useEffect(() => {
    if (!connected) return;
    let stopped = false;
    const check = () =>
      aiApi
        .ready()
        .then((r) => !stopped && setAiReady({ ready: r.ready, message: r.ready ? null : r.message }))
        .catch(() => !stopped && setAiReady({ ready: null, message: null }));
    void check();
    const timer = window.setInterval(() => {
      void check();
      reloadAi(); // the label follows changes made elsewhere too
    }, AI_EVERY_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [aiKey, connected, reloadAi]);

  // Once when the app opens: is there a newer version? (Asks GitHub at most once a day, if switched on.)
  useEffect(() => {
    updatesApi.status().then(setUpdates).catch(() => undefined);
  }, []);

  // The sidebar numbers catch up on every page change, platform change and organising.
  const refreshCounts = useCallback(() => {
    libraryApi
      .overview()
      .then((o) => setCounts(o.counts))
      .catch(() => undefined);
  }, []);
  useEffect(refreshCounts, [route.path, scope.platform, refreshCounts]);
  useEffect(() => onOrganizeChange(refreshCounts), [refreshCounts]);
  // A finished import can add a platform to the picker.
  useEffect(() => {
    if (route.path === "/import" || route.path === "/library") reloadScope();
  }, [route.path, reloadScope]);

  // Open on the screen chosen in Settings -> Appearance.
  const startHandled = useRef(false);
  useEffect(() => {
    if (!lookLoaded || startHandled.current) return;
    startHandled.current = true;
    const atStart = !window.location.hash || window.location.hash === "#/" || window.location.hash === "#/home";
    if (atStart) navigate(`/${look.start_page}`);
  }, [lookLoaded, look.start_page]);

  // A new theme spreads out from the theme button in the sidebar's corner.
  const setTheme = useCallback(
    (theme: ThemeChoice) =>
      revealTheme(() => {
        applyTheme(theme); // on the page straight away, for the reveal
        changeLook({ theme });
      }),
    [changeLook],
  );
  const cycleTheme = useCallback(() => setTheme(nextTheme(look.theme)), [look.theme, setTheme]);
  const sections: NavSection[] = useMemo(
    () =>
      buildSections(counts).map((section) => ({
        ...section,
        items: arrangeNav(section.items, look.nav_order, look.nav_hidden),
      })),
    [counts, look.nav_order, look.nav_hidden],
  );
  const nav = useMemo(() => sections.flatMap((s) => s.items), [sections]);

  const tips = useMemo(
    () => ({
      dismissed: look.dismissed_tips,
      dismiss: (id: string) => changeLook({ dismissed_tips: [...look.dismissed_tips.filter((t) => t !== id), id] }),
    }),
    [look.dismissed_tips, changeLook],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (showTutorial) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey && !event.shiftKey && key === "k") || (event.key === "/" && !typing(event.target) && !event.ctrlKey && !event.altKey)) {
        // Ctrl+K or "/" opens the command centre (Ctrl+K again closes it).
        event.preventDefault();
        setShowCommands((open) => (event.ctrlKey ? !open : true));
      } else if (event.ctrlKey && event.shiftKey && key === "d") {
        // Ctrl+Shift+D opens the hidden developer page.
        event.preventDefault();
        navigate("/dev");
      } else if (event.ctrlKey && event.shiftKey && key === "l") {
        event.preventDefault();
        cycleTheme();
      } else if (event.altKey && !event.ctrlKey && /^[1-9]$/.test(event.key)) {
        const target = nav[Number(event.key) - 1];
        if (target) {
          event.preventDefault();
          navigate(target.path);
        }
      } else if (event.key === "?" && !typing(event.target)) {
        event.preventDefault();
        setShowShortcuts(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cycleTheme, nav, showTutorial]);

  useEffect(() => {
    // A file dropped outside the Import screen would make the window open
    // that file and leave the app. Stop that.
    const stop = (event: DragEvent) => event.preventDefault();
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => {
      window.removeEventListener("dragover", stop);
      window.removeEventListener("drop", stop);
    };
  }, []);

  // What the command centre can do, besides finding things.
  const commands = useMemo<CommandAction[]>(() => {
    const go = (path: string) => () => navigate(path);
    return [
      ...nav.map((item, index) => ({
        id: `go-${item.path}`,
        label: `Go to ${item.label}`,
        icon: item.icon,
        keys: index < 9 ? `Alt ${index + 1}` : undefined,
        words: "open page",
        run: go(item.path),
      })),
      { id: "new-plan", label: "Make a plan", icon: icons.plans, words: "new create todo list", run: go("/plans") },
      { id: "import", label: "Import saves", icon: icons.import, words: "add bring in export file tiktok instagram youtube", run: go("/import") },
      { id: "transcripts", label: "Sort: transcripts, AI notes and suggestions", icon: icons.transcripts, words: "transcribe ai notes sort approve unsorted", run: go("/transcripts") },
      { id: "ask", label: "Ask the AI Assistant", icon: icons.sparkle, words: "chat question", run: go("/chat") },
      { id: "organise", label: "Organise collections", icon: icons.folder, words: "sort file folders spaces", run: go("/collections") },
      { id: "review", label: "Saves that need review", icon: icons.review, words: "check ai unsure", run: go("/collections/review") },
      { id: "no-collection", label: "Saves in no collection", icon: icons.folderMinus, words: "unsorted loose", run: go("/library?collection_id=none") },
      { id: "not-transcribed", label: "Saves not transcribed yet", icon: icons.clock, words: "waiting", run: go("/library?status=waiting") },
      { id: "theme-light", label: "Light theme", icon: icons.sun, words: "appearance mode bright", run: () => setTheme("light") },
      { id: "theme-dark", label: "Dark theme", icon: icons.moon, words: "appearance mode night", run: () => setTheme("dark") },
      { id: "theme-system", label: "Theme: same as Windows", icon: icons.monitor, words: "appearance mode system auto", run: () => setTheme("system") },
      {
        id: "sidebar",
        label: look.compact_sidebar ? "Wide sidebar" : "Slim sidebar",
        icon: icons.sidebar,
        words: "compact icons only",
        run: () => changeLook({ compact_sidebar: !look.compact_sidebar }),
      },
      { id: "settings-ai", label: "Settings: AI", icon: icons.settings, words: "model ollama key cloud", run: go("/settings?section=ai") },
      { id: "settings-look", label: "Settings: Appearance", icon: icons.settings, words: "accent colour color text size", run: go("/settings?section=appearance") },
      { id: "settings-storage", label: "Settings: Storage", icon: icons.settings, words: "space disk files data folder", run: go("/settings?section=storage") },
      updates?.update_available && updates.can_install
        ? { id: "update", label: `Update Keptwise to ${updates.latest}`, icon: icons.download, words: "upgrade new version install", run: () => void updatesApi.install().catch(() => navigate("/settings?section=updates")) }
        : { id: "check-updates", label: "Check for updates", icon: icons.download, words: "upgrade new version", run: () => void updatesApi.checkNow().then(setUpdates).catch(() => undefined) },
      { id: "tutorial", label: "Guided tutorial", icon: icons.bulb, words: "help getting started tour tutorial", run: openTutorial },
      { id: "shortcuts", label: "Keyboard shortcuts", icon: icons.keyboard, keys: "?", words: "keys help", run: () => setShowShortcuts(true) },
    ];
  }, [nav, look.compact_sidebar, changeLook, setTheme, updates, openTutorial]);

  const page = route.parts[0] === "home" || !route.parts[0] ? "library" : route.parts[0];
  const itemId = page === "item" ? Number(route.parts[1]) : NaN;
  const planId = page === "plans" && route.parts[1] ? Number(route.parts[1]) : NaN;
  let content;
  if (page === "dev") content = <DevPage />;
  else if (page === "item" && Number.isInteger(itemId)) content = <ItemPage itemId={itemId} />;
  else if (page === "plans" && Number.isInteger(planId)) content = <PlanPage planId={planId} />;
  else if (page === "plans") content = <PlansPage />;
  else if (page === "unsave") content = <UnsavePage />;
  else if (page === "archive") content = <ArchivePage tab={route.parts[1] ?? null} cardSize={look.card_size} />;
  else if (page === "import") content = <ImportPage />;
  else if (page === "transcripts" || page === "sort") content = <TranscriptsPage />;
  else if (page === "collections") content = <CollectionsPage selection={route.parts[1] ?? null} />;
  else if (page === "tags") content = <TagsPage />;
  else if (page === "search") content = <SearchPage />;
  else if (page === "chat" || page === "assistant")
    content = <AssistantPage chatId={route.parts[1] ? Number(route.parts[1]) : null} />;
  else if (page === "settings")
    content = (
      <SettingsPage
        overview={overview}
        onAiChange={setOverview}
        look={look}
        onLookChange={changeLook}
        updates={updates}
        onUpdatesChange={setUpdates}
        onTutorial={openTutorial}
      />
    );
  else content = <LibraryPage cardSize={look.card_size} cardActions={look.card_actions} name={look.name} />;

  // An item page belongs to the Library in the sidebar.
  const activePath = page === "item" ? "/library" : page === "assistant" ? "/chat" : `/${page}`;
  const status: LiveStatus = {
    connected,
    aiLabel: overview?.current_label ?? "…",
    aiReady: aiReady.ready,
    aiMessage: aiReady.message,
    checkedAt,
  };

  const compactSidebar = look.compact_sidebar || narrowWindow;
  return (
    <TipsProvider value={tips}>
      <Layout
        sections={sections}
        activePath={activePath}
        status={status}
        onSearch={() => setShowCommands(true)}
        picker={<PlatformPicker scope={scope} onChoose={chooseScope} compact={compactSidebar} />}
        theme={look.theme}
        compact={compactSidebar}
        onCycleTheme={cycleTheme}
        onShortcuts={() => setShowShortcuts(true)}
        onReorderNav={(paths) => changeLook({ nav_order: paths })}
        onStatusClick={() => navigate("/settings?section=ai")}
        footer={updates && !compactSidebar ? <UpdateNow status={updates} place="sidebar" /> : undefined}
        actions={<UndoButtons />}
      >
        {/* key: each page starts at the top, with fresh state, and reloads when the platform changes */}
        <div key={`${page === "item" || page === "plans" ? route.path : page}|${scope.platform ?? "all"}|${dataVersion}`} className={`kw-page ${page === "collections" || page === "chat" || page === "assistant" ? "h-full" : ""}`}>
          {content}
        </div>
      </Layout>
      {welcome && <Welcome look={look} onChange={changeLook} onTheme={setTheme} cloud={overview?.current_kind === "cloud"} />}
      {showWizard && (
        <SetupWizard overview={overview} onChange={setOverview} onFinish={() => setWizardClosed(true)} />
      )}
      {showTutorial && <GuidedTour onClose={closeTutorial} />}
      {showCommands && !showTutorial && <CommandPalette actions={commands} onClose={() => setShowCommands(false)} />}
      {showShortcuts && !showTutorial && <ShortcutsDialog onClose={() => setShowShortcuts(false)} />}
      <Toasts />
    </TipsProvider>
  );
}
