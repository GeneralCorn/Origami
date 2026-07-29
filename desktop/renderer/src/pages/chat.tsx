import { useParams } from "@/lib/router";

import WorkspaceLayout from "@/components/layout/workspace-layout";

export default function ChatPage() {
  const { id } = useParams<{ id: string }>();
  return <WorkspaceLayout chatId={id} />;
}
