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
