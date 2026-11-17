import { expect, test } from "vitest";

import { dropName, filesFromDrop, pickWanted, type DroppedFile } from "./importApi";

const info = {
  wanted_names: ["user_data_tiktok.json", "saved_posts.json", "favorite videos.txt"],
  wanted_extensions: [".zip", ".csv"],
};

const dropped = (path: string): DroppedFile => ({
  file: new File(["x"], path.split("/").pop() ?? path),
  path,
});

test("from a folder only the files the importers read are sent", () => {
  const files = [
    dropped("instagram/your_instagram_activity/saved/saved_posts.json"),
    dropped("instagram/media/posts/photo.jpg"),
    dropped("instagram/your_instagram_activity/messages/inbox/ana/message_1.json"),
    dropped("export/Activity/Favorite Videos.txt"),
    dropped("Takeout/YouTube and YouTube Music/playlists/Watch later-videos.csv"),
    dropped("downloads/tiktok.zip"),
  ];
  expect(pickWanted(files, info).map((f) => f.path)).toEqual([
    "instagram/your_instagram_activity/saved/saved_posts.json",
    "export/Activity/Favorite Videos.txt",
    "Takeout/YouTube and YouTube Music/playlists/Watch later-videos.csv",
    "downloads/tiktok.zip",
  ]);
});

test("a file dropped on its own is always sent", () => {
  expect(pickWanted([dropped("my export.json")], info)).toHaveLength(1);
});

test("names what was dropped", () => {
  expect(dropName([dropped("tiktok.zip")])).toBe("tiktok.zip");
  expect(dropName([dropped("insta/a.json"), dropped("insta/b/c.json")])).toBe("insta");
  expect(dropName([dropped("a.zip"), dropped("b.zip")])).toBe("2 files");
});

test("reads every file inside a dropped folder", async () => {
  const fileEntry = (fullPath: string) => ({
    isFile: true,
    isDirectory: false,
    name: fullPath.split("/").pop(),
    fullPath,
    file: (resolve: (file: File) => void) => resolve(new File(["x"], fullPath.split("/").pop() ?? "")),
  });
  const children = [fileEntry("/export/a.json"), fileEntry("/export/sub/b.csv")];
  let handedOut = false;
  const folder = {
    isFile: false,
    isDirectory: true,
    name: "export",
    fullPath: "/export",
    createReader: () => ({
      // Like the real thing: entries come in batches until an empty one.
      readEntries: (resolve: (entries: unknown[]) => void) => {
        resolve(handedOut ? [] : children);
        handedOut = true;
      },
    }),
  };
  const data = {
    items: [{ kind: "file", webkitGetAsEntry: () => folder }],
    files: [],
  } as unknown as DataTransfer;

  const files = await filesFromDrop(data);
  expect(files.map((f) => f.path)).toEqual(["export/a.json", "export/sub/b.csv"]);
});
