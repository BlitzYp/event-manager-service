import type { EmailBlock, EmailDocument } from "../types";

export type BlockType = "Heading" | "Text" | "Button" | "Image" | "Divider" | "Spacer" | "Html";

// Starter content and supported personalization tokens.
export const starterDocument: EmailDocument = {
  root: {
    type: "EmailLayout",
    data: {
      backdropColor: "#eef2ee",
      canvasColor: "#ffffff",
      textColor: "#24342d",
      fontFamily: "MODERN_SANS",
      childrenIds: ["welcome-heading", "welcome-text", "wallet-button"],
    },
  },
  "welcome-heading": {
    type: "Heading",
    data: {
      props: { level: "h2", text: "Hello, {{participant_first_name}}!" },
      style: {
        padding: { top: 32, right: 32, bottom: 12, left: 32 },
        fontWeight: "bold",
      },
    },
  },
  "welcome-text": {
    type: "Text",
    data: {
      props: { text: "Your event wallet is ready.", markdown: true },
      style: {
        padding: { top: 0, right: 32, bottom: 20, left: 32 },
        fontSize: 16,
      },
    },
  },
  "wallet-button": {
    type: "Button",
    data: {
      props: {
        text: "Open wallet",
        url: "{{wallet_link}}",
        buttonBackgroundColor: "#4fa800",
        buttonTextColor: "#ffffff",
        buttonStyle: "rounded",
        size: "large",
      },
      style: {
        padding: { top: 8, right: 32, bottom: 32, left: 32 },
        textAlign: "left",
      },
    },
  },
};

export const placeholders = [
  ["First name", "{{participant_first_name}}"],
  ["Last name", "{{participant_last_name}}"],
  ["Full name", "{{participant_name}}"],
  ["Participant code", "{{participant_code}}"],
  ["Email", "{{participant_email}}"],
  ["Group", "{{participant_group}}"],
  ["Event name", "{{event_name}}"],
] as const;

/** Return fresh editable content and styles for one newly added block. */
export function defaultBlock(type: BlockType): EmailBlock {
  const padding = { top: 16, right: 24, bottom: 16, left: 24 };
  if (type === "Heading")
    return { type, data: { props: { text: "New heading", level: "h2" }, style: { padding } } };
  if (type === "Text")
    return { type, data: { props: { text: "New text block", markdown: true }, style: { padding, fontSize: 16 } } };
  if (type === "Button")
    return {
      type,
      data: {
        props: {
          text: "Open",
          url: "https://example.com",
          buttonBackgroundColor: "#4fa800",
          buttonTextColor: "#ffffff",
          buttonStyle: "rounded",
          size: "medium",
        },
        style: { padding },
      },
    };
  if (type === "Image")
    return {
      type,
      data: {
        props: { url: "https://placehold.co/600x300/png", alt: "Image", contentAlignment: "middle" },
        style: { padding },
      },
    };
  if (type === "Divider")
    return { type, data: { props: { lineColor: "#d7ded9", lineHeight: 1 }, style: { padding } } };
  if (type === "Spacer") return { type, data: { props: { height: 32 } } };
  return {
    type,
    data: { props: { contents: "<p>Custom HTML content</p>" }, style: { padding } },
  };
}

/** Substitute demonstration values for a browser preview; delivery uses server-side values. */
export function sampleHtml(source: string) {
  return source
    .replaceAll("{{participant_first_name}}", "Anna")
    .replaceAll("{{participant_last_name}}", "Bērziņa")
    .replaceAll("{{participant_name}}", "Anna Bērziņa")
    .replaceAll("{{participant_code}}", "P-1042")
    .replaceAll("{{participant_email}}", "anna@example.com")
    .replaceAll("{{participant_group}}", "Guests")
    .replaceAll("{{event_name}}", "Summer event")
    .replaceAll("{{wallet_link}}", "https://example.com/wallet");
}

