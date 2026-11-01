// Lane A production entry: mounts App inside the locale provider and the
// shared ApiClient entry (HTTP client) under the browser router.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "./ApiClientProvider";
import { HttpApiClient } from "../api/client";
import { LocaleProvider } from "../locale/index";
import { App } from "./App";
import "../ui/tokens.css";
import "../ui/base.css";
import "../ui/shell.css";
import { applyTheme, readTheme } from "../shell/theme";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("app root element is missing");
}

// Single coherent theme before first paint: explicit data-theme on the
// root (dark default), so cards never sit on an unthemed page.
applyTheme(readTheme());

const client = new HttpApiClient();

const router = createBrowserRouter([{ path: "*", element: <App /> }]);

createRoot(rootElement).render(
  <StrictMode>
    <LocaleProvider>
      <ApiClientProvider client={client}>
        <RouterProvider router={router} />
      </ApiClientProvider>
    </LocaleProvider>
  </StrictMode>,
);
