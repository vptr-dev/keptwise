import "@fontsource-variable/inter";
// Entry point: puts the App on the page.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error('index.html is missing <div id="root">');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
