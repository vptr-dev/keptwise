// Plain steps for getting each platform's export. Menu names can change a
// little over time; the page says so.
export type Guide = {
  platform: string;
  name: string;
  steps: string[];
  wait: string;
};

export const GUIDES: Guide[] = [
  {
    platform: "tiktok",
    name: "TikTok",
    steps: [
      "In the TikTok app, open your Profile and tap the ☰ menu.",
      "Go to Settings and privacy → Account → Download your data.",
      "Pick JSON as the file format, then tap Request data.",
      "When it's ready, open the Download data tab and download the zip.",
    ],
    wait: "TikTok can take up to a few days to prepare it.",
  },
  {
    platform: "instagram",
    name: "Instagram",
    steps: [
      "In Instagram, go to Settings → Accounts Center → Your information and permissions → Download your information.",
      "Choose Download or transfer information, pick your Instagram account, then Some of your information.",
      "Tick Saved (under Your Instagram activity), then Download to device.",
      "Set Date range to All time and Format to JSON, then Create files. Download the zip when Meta emails you.",
    ],
    wait: "Usually ready within a few hours.",
  },
  {
    platform: "facebook",
    name: "Facebook",
    steps: [
      "In Facebook, go to Settings → Accounts Center → Your information and permissions → Download your information.",
      "Choose Download or transfer information, pick your Facebook account, then Some of your information.",
      "Tick Saved items and collections, then Download to device.",
      "Set Date range to All time and Format to JSON, then Create files. Download the zip when Meta emails you.",
    ],
    wait: "Usually ready within a few hours.",
  },
  {
    platform: "youtube",
    name: "YouTube",
    steps: [
      "Go to takeout.google.com and click Deselect all.",
      "Scroll down and tick YouTube and YouTube Music.",
      "Click All YouTube data included, keep only playlists, and press OK.",
      "Click Next step, keep Export once and .zip, then Create export. Download the zip from Google's email.",
    ],
    wait: "Playlists alone are usually ready within minutes.",
  },
];
