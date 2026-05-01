import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";

// ── Lightweight standalone Button for story purposes ─────────────────────────
// We story the raw button variants rather than a custom component so stories
// demonstrate the *CSS design system* rather than any specific component logic.

type ButtonProps = {
  label: string;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  small?: boolean;
  onClick?: () => void;
};

function Button({ label, variant = "primary", disabled = false, small = false, onClick }: ButtonProps) {
  const cls = [
    variant === "primary" ? "primary-button" : variant === "danger" ? "danger-button" : "secondary-button",
    small ? "small-button" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={cls} disabled={disabled} onClick={onClick} type="button">
      {label}
    </button>
  );
}

const meta = {
  title: "Design System/Button",
  component: Button,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "danger"],
    },
  },
  args: { onClick: fn() },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    label: "Upload document",
    variant: "primary",
  },
};

export const Secondary: Story = {
  args: {
    label: "Refresh",
    variant: "secondary",
  },
};

export const Danger: Story = {
  args: {
    label: "Delete",
    variant: "danger",
  },
};

export const Small: Story = {
  args: {
    label: "Re-index",
    variant: "secondary",
    small: true,
  },
};

export const Disabled: Story = {
  args: {
    label: "Send",
    variant: "primary",
    disabled: true,
  },
};
