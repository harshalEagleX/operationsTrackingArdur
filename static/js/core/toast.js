/**
 * Toasts. This is what replaces alert().
 *
 * alert() blocks the page, steals focus, cannot be styled, cannot carry an
 * action, and on a second failure queues up behind the first. A toast does
 * none of that.
 *
 * Message guidance: say what happened and what to do next, in the interface's
 * own voice.
 *   Good: "Couldn't save the project — a project with this ID already exists."
 *   Bad:  "Error!"  /  "Sorry, something went wrong."
 */

const DEFAULT_TIMEOUT = 5000;
const ERROR_TIMEOUT = 8000;

function host() {
  let element = document.getElementById("toast-host");
  if (!element) {
    element = document.createElement("div");
    element.id = "toast-host";
    element.className = "toast-host";
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
    document.body.appendChild(element);
  }
  return element;
}

export const toast = {
  show(message, { type = "info", timeout = DEFAULT_TIMEOUT, action = null } = {}) {
    const element = document.createElement("div");
    element.className = `toast toast-${type}`;

    const text = document.createElement("span");
    // textContent, never innerHTML — a message may contain a filename or a
    // value the user typed.
    text.textContent = message;
    element.appendChild(text);

    if (action) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "toast-action";
      button.textContent = action.label;
      button.addEventListener("click", () => {
        action.onClick();
        dismiss();
      });
      element.appendChild(button);
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Dismiss");
    close.textContent = "×";
    close.addEventListener("click", () => dismiss());
    element.appendChild(close);

    host().appendChild(element);

    let timer = null;
    const dismiss = () => {
      if (timer) clearTimeout(timer);
      element.classList.add("toast-leaving");
      // Wait for the CSS transition rather than a magic number.
      element.addEventListener("transitionend", () => element.remove(), { once: true });
      // Belt and braces if the element has no transition (reduced motion).
      setTimeout(() => element.remove(), 400);
    };

    if (timeout > 0) timer = setTimeout(dismiss, timeout);

    // Do not time out while the pointer is on it — the user is reading.
    element.addEventListener("mouseenter", () => timer && clearTimeout(timer));
    element.addEventListener("mouseleave", () => {
      if (timeout > 0) timer = setTimeout(dismiss, timeout);
    });

    return dismiss;
  },

  success(message, options) {
    return this.show(message, { ...options, type: "success" });
  },

  error(message, options) {
    return this.show(message, { ...options, type: "error", timeout: ERROR_TIMEOUT });
  },

  warning(message, options) {
    return this.show(message, { ...options, type: "warning" });
  },

  info(message, options) {
    return this.show(message, { ...options, type: "info" });
  },
};
