/**
 * Login form.
 *
 * Submits over the API rather than a form POST so the error envelope renders
 * in place, without a page reload that would lose what was typed.
 */

import { ApiError, api } from "../core/api.js";
import { toast } from "../core/toast.js";

const form = document.getElementById("login-form");
const errorBox = document.getElementById("login-error");
const submit = document.getElementById("login-submit");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();

  errorBox.hidden = true;
  submit.disabled = true;
  submit.textContent = "Signing in…";

  const data = new FormData(form);

  try {
    const user = await api.post("/auth/login/", {
      emp_id: String(data.get("emp_id")).trim(),
      password: data.get("password"),
    });

    // Honour ?next= if it is a same-site path. Never redirect to an absolute
    // URL from a query parameter — that is an open redirect.
    const next = String(data.get("next") || "");
    const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : null;

    window.location.href =
      safeNext || (user.is_supervisor ? "/dashboard/" : "/userdashboard/");
  } catch (error) {
    if (error instanceof ApiError) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
      form.querySelector("#password").value = "";
      form.querySelector("#password").focus();
    } else {
      toast.error("Could not reach the server. Check your connection and try again.");
    }
  } finally {
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
});
