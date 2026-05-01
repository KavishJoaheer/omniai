import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "../src/components/CommandPalette";

const meta = {
  title: "Components/CommandPalette",
  component: CommandPalette,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  args: {
    onClose: fn(),
  },
} satisfies Meta<typeof CommandPalette>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {
  args: {
    open: true,
  },
};

export const Closed: Story = {
  args: {
    open: false,
  },
};

export const WithExtraCommands: Story = {
  args: {
    open: true,
    extraCommands: [
      {
        id: "bulk-delete",
        label: "Bulk delete selected",
        category: "Action",
        icon: "🗑️",
        action: fn(),
      },
      {
        id: "export-chat",
        label: "Export conversation as Markdown",
        category: "Action",
        icon: "⬇️",
        action: fn(),
      },
    ],
  },
};
