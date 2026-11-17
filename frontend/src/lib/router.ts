// A tiny page router using the part of the address after "#",
// e.g. "#/item/12". No extra library needed.
import { useEffect, useState } from "react";

export type Route = {
  path: string; // "/item/12"
  parts: string[]; // ["item", "12"]
  query: URLSearchParams;
};

function readRoute(): Route {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [pathPart, queryPart = ""] = raw.split("?");
  const path = pathPart.startsWith("/") ? pathPart : `/${pathPart}`;
  return {
    path,
    parts: path.split("/").filter(Boolean),
    query: new URLSearchParams(queryPart),
  };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = path;
}
