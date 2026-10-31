// OC-K07 (R-372): third-party notices shipped with the K07 bundle.
// Versions are read from frontend/package.json, so they can never drift
// from the pin; licences are the declared project licences. Adding a
// runtime dependency without a licence entry here fails the About test,
// which asserts every runtime entry is listed.

import packageJson from "../../package.json";

export interface ThirdPartyNotice {
  name: string;
  version: string;
  licence: string;
}

const LICENCES: Record<string, string> = {
  react: "MIT",
  "react-router-dom": "MIT",
  zod: "MIT",
};

const DEPENDENCIES: Record<string, string> = packageJson.dependencies as Record<
  string,
  string
>;

export const THIRD_PARTY_NOTICES: readonly ThirdPartyNotice[] =
  Object.keys(DEPENDENCIES)
    .sort()
    .map((name) => ({
      name,
      version: DEPENDENCIES[name].replace(/^[~^]/, ""),
      licence: LICENCES[name] ?? "SEE PACKAGE LICENCE",
    }));
