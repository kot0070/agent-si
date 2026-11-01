/** K03 STEP2: ASK decision buttons (buttons only, no resume logic).
 *
 * The three permission decisions as button descriptors, in button order.
 * Selecting a button forwards its exact decision id to the caller's
 * onDecision handler; resume itself lives in
 * src/agent_si/test_runners/ask_resume.py. Record schemas stay with K13
 * and the execution writer stays with K06. The owning shell/chat lane
 * renders these descriptors; this module never holds settings controls.
 *
 * @typedef {"allow_once" | "allow_project" | "deny"} AskDecisionId
 * @typedef {{ id: AskDecisionId, label: string }} AskDecision
 * @typedef {{ runId: string, onDecision: (id: AskDecisionId) => void }} AskButtonsProps
 * @typedef {{ id: AskDecisionId, label: string, select: () => void }} AskButtonDescriptor
 */

/** The three decisions in button order. */
export function askDecisions() {
  return [
    { id: "allow_once", label: "Allow once" },
    { id: "allow_project", label: "For this project" },
    { id: "deny", label: "Deny" },
  ];
}

/**
 * @param {AskButtonsProps} props
 * @returns {AskButtonDescriptor[]} one descriptor per decision, in order;
 * calling select() on one invokes props.onDecision with its id.
 */
export function AskButtons(props) {
  return askDecisions().map((decision) => ({
    id: decision.id,
    label: decision.label,
    select: () => props.onDecision(decision.id),
  }));
}

export const ASK_BUTTON_ENTRY = "frontend/src/teststage/ask_buttons.jsx";

/** DEMOF13F1 F13: install-permission ask-once wiring.
 *
 * The ASK buttons call POST /api/v1/permissions/check on click and
 * disable once the reply reports asked_once true: the first reply
 * carries asked_once false and repeats carry true.
 */
export const ASK_CHECK_ROUTE = "/api/v1/permissions/check";

/**
 * Ask install permission for one tool id.
 * @param {string} toolId
 * @returns {Promise<{ allowed: boolean, askedOnce: boolean }>}
 */
export async function askPermission(toolId) {
  const res = await fetch(ASK_CHECK_ROUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_id: toolId }),
  });
  if (!res.ok) {
    throw new Error("permission check failed: " + res.status);
  }
  const data = await res.json();
  return {
    allowed: data.allowed === true,
    askedOnce: data.asked_once === true,
  };
}

/**
 * @param {{ runId: string, toolId: string, onDecision: (id: AskDecisionId) => void }} props
 * @returns {Array<{ id: AskDecisionId, label: string, isDisabled: () => boolean, select: () => Promise<{ allowed: boolean, askedOnce: boolean }> }>}
 * descriptors like AskButtons, but select() asks permission first and
 * the buttons disable after the reply reports asked_once true.
 */
export function AskButtonsWithPermission(props) {
  let disabled = false;
  const descriptors = AskButtons({
    runId: props.runId,
    onDecision: (id) => props.onDecision(id),
  });
  return descriptors.map((item) => ({
    id: item.id,
    label: item.label,
    isDisabled: () => disabled,
    select: async () => {
      if (disabled) {
        return { allowed: false, askedOnce: true };
      }
      const outcome = await askPermission(props.toolId);
      if (outcome.askedOnce) {
        disabled = true;
      }
      props.onDecision(item.id);
      return outcome;
    },
  }));
}
