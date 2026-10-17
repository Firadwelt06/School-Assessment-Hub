import { D1PortalStore, R2ImageStore } from "./cloudflare-store.js";
import { handleRequest } from "./index.js";
import type { PortalEnv } from "./portal-store.js";

interface Env {
  DB: D1Database;
  SUBMISSION_IMAGES: R2Bucket;
  SCHOOL_SIGNUP_CODE: string;
  SYNC_TOKEN: string;
}

export default {
  fetch(request: Request, bindings: Env) {
    const env: PortalEnv = {
      store: new D1PortalStore(bindings.DB),
      images: new R2ImageStore(bindings.SUBMISSION_IMAGES),
      SCHOOL_SIGNUP_CODE: bindings.SCHOOL_SIGNUP_CODE,
      SYNC_TOKEN: bindings.SYNC_TOKEN,
    };
    return handleRequest(request, env);
  },
};
