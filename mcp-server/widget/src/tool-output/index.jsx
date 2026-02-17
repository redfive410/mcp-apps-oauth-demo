import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { useApp } from "@modelcontextprotocol/ext-apps/react";
import ToolOutputWidget from "./widget";

function ToolOutputWidgetWrapper() {
  const { app, isConnected, error: connectionError } = useApp({
    appInfo: { name: "Tool Output", version: "1.0.0" },
    capabilities: {},
  });
  const [toolResult, setToolResult] = useState(null);
  const [toolError, setToolError] = useState(null);

  useEffect(() => {
    if (!app) return;

    app.ontoolresult = (params) => {
      if (params?.isError) {
        setToolError(params.content?.[0]?.text || "An error occurred");
        setToolResult(null);
      } else {
        setToolResult(params);
        setToolError(null);
      }
    };
  }, [app]);

  if (connectionError) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "red" }}>
        Connection error: {connectionError.message}
      </div>
    );
  }

  if (!isConnected) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "#666" }}>
        Connecting to host...
      </div>
    );
  }

  if (toolError) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "red" }}>
        Error: {toolError}
      </div>
    );
  }

  return <ToolOutputWidget toolResult={toolResult} />;
}

const root = createRoot(document.getElementById("tool-output-root"));
root.render(<ToolOutputWidgetWrapper />);

export default ToolOutputWidgetWrapper;
