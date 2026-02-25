import WorkspaceLayout from "@/components/layout/workspace-layout";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function ChatPage({ params }: Props) {
  const { id } = await params;
  return <WorkspaceLayout chatId={id} />;
}
