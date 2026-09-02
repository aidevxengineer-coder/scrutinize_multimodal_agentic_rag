import { useEffect, useState } from "react";
import {
  getProjectTools,
  createProjectTool,
  updateProjectTool,
  toggleProjectTool,
  deleteProjectTool,
} from "../api/client";
import type { ProjectTool, ExecutionMode } from "../types/api";

const DEFAULT_SCHEMA_JSON = JSON.stringify(
  {
    type: "object",
    properties: {
      sku: {
        type: "string",
        description: "Product SKU identifier (e.g. SKU-9823)",
      },
    },
    required: ["sku"],
  },
  null,
  2
);

export function CustomToolsView({ projectId }: { projectId: string }) {
  const [tools, setTools] = useState<ProjectTool[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingTool, setEditingTool] = useState<ProjectTool | null>(null);

  // Form State
  const [name, setName] = useState<string>("");
  const [displayName, setDisplayName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("client_delegated");
  const [webhookUrl, setWebhookUrl] = useState<string>("");
  const [webhookMethod, setWebhookMethod] = useState<string>("POST");
  const [webhookHeadersJson, setWebhookHeadersJson] = useState<string>("{}");
  const [schemaJson, setSchemaJson] = useState<string>(DEFAULT_SCHEMA_JSON);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (projectId && projectId !== "undefined") {
      fetchTools();
    }
  }, [projectId]);

  const fetchTools = async () => {
    if (!projectId || projectId === "undefined") return;
    try {
      setLoading(true);
      setError(null);
      const data = await getProjectTools(projectId);
      setTools(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load project custom tools.");
    } finally {
      setLoading(false);
    }
  };


  const handleOpenCreateModal = () => {
    setEditingTool(null);
    setName("");
    setDisplayName("");
    setDescription("");
    setExecutionMode("client_delegated");
    setWebhookUrl("");
    setWebhookMethod("POST");
    setWebhookHeadersJson("{}");
    setSchemaJson(DEFAULT_SCHEMA_JSON);
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (tool: ProjectTool) => {
    setEditingTool(tool);
    setName(tool.name);
    setDisplayName(tool.display_name);
    setDescription(tool.description);
    setExecutionMode(tool.execution_mode);
    setWebhookUrl(tool.webhook_url || "");
    setWebhookMethod(tool.webhook_method || "POST");
    setWebhookHeadersJson(JSON.stringify(tool.webhook_headers || {}, null, 2));
    setSchemaJson(JSON.stringify(tool.parameters_schema || {}, null, 2));
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleToggle = async (tool: ProjectTool) => {
    try {
      const updated = await toggleProjectTool(projectId, tool.id, !tool.is_enabled);
      setTools((prev) => prev.map((t) => (t.id === tool.id ? updated : t)));
    } catch (err: any) {
      alert(err?.message || "Failed to toggle tool status.");
    }
  };

  const handleDelete = async (tool: ProjectTool) => {
    if (!confirm(`Are you sure you want to delete the custom tool '${tool.display_name}'?`)) {
      return;
    }
    try {
      await deleteProjectTool(projectId, tool.id);
      setTools((prev) => prev.filter((t) => t.id !== tool.id));
    } catch (err: any) {
      alert(err?.message || "Failed to delete tool.");
    }
  };

  const handleSubmitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    let parsedSchema: Record<string, any>;
    try {
      parsedSchema = JSON.parse(schemaJson);
    } catch {
      setFormError("Invalid JSON syntax in Parameters JSON Schema.");
      return;
    }

    let parsedHeaders: Record<string, string> = {};
    if (executionMode === "server_webhook" && webhookHeadersJson.trim()) {
      try {
        parsedHeaders = JSON.parse(webhookHeadersJson);
      } catch {
        setFormError("Invalid JSON syntax in Webhook Headers.");
        return;
      }
    }

    setSubmitting(true);
    try {
      if (editingTool) {
        const updated = await updateProjectTool(projectId, editingTool.id, {
          name,
          display_name: displayName,
          description,
          execution_mode: executionMode,
          webhook_url: executionMode === "server_webhook" ? webhookUrl : null,
          webhook_method: executionMode === "server_webhook" ? webhookMethod : null,
          webhook_headers: executionMode === "server_webhook" ? parsedHeaders : null,
          parameters_schema: parsedSchema,
        });
        setTools((prev) => prev.map((t) => (t.id === editingTool.id ? updated : t)));
      } else {
        const created = await createProjectTool(projectId, {
          name,
          display_name: displayName,
          description,
          is_enabled: true,
          execution_mode: executionMode,
          webhook_url: executionMode === "server_webhook" ? webhookUrl : null,
          webhook_method: executionMode === "server_webhook" ? webhookMethod : null,
          webhook_headers: executionMode === "server_webhook" ? parsedHeaders : null,
          parameters_schema: parsedSchema,
        });
        setTools((prev) => [...prev, created]);
      }
      setIsModalOpen(false);
    } catch (err: any) {
      setFormError(err?.message || "Failed to save tool configuration.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-200 pb-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900">Custom Project Tools</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Register and manage dynamic tool schemas for agentic reasoning and API dispatches.
          </p>
        </div>
        <button
          onClick={handleOpenCreateModal}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom Tool
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-900 border-t-transparent"></div>
        </div>
      ) : tools.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-zinc-50/50 p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-100 text-zinc-600">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 4a2 2 0 114 0v1a2 2 0 002 2h3a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V9a2 2 0 012-2h3a2 2 0 002-2V4z" />
            </svg>
          </div>
          <h3 className="mt-3 text-sm font-medium text-zinc-900">No Custom Tools Defined</h3>
          <p className="mt-1 text-xs text-zinc-500 max-w-md mx-auto">
            Define custom tool specifications to allow Scrutinize to autonomously invoke your API functions.
          </p>
          <button
            onClick={handleOpenCreateModal}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-50"
          >
            + Create First Tool
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2">
          {tools.map((tool) => (
            <div
              key={tool.id}
              className={`flex flex-col justify-between rounded-2xl border p-5 shadow-sm transition-all ${
                tool.is_enabled ? "border-zinc-200 bg-white" : "border-zinc-200/70 bg-zinc-50/80 opacity-75"
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-zinc-900 flex items-center gap-2">
                      {tool.display_name}
                      <span className="font-mono text-[11px] font-normal text-zinc-400">({tool.name})</span>
                    </h3>
                    <div className="mt-1.5 flex items-center gap-2">
                      <span
                        className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${
                          tool.execution_mode === "server_webhook"
                            ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                            : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        }`}
                      >
                        {tool.execution_mode === "server_webhook" ? "Server Webhook" : "Client Delegated"}
                      </span>

                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-medium ${
                          tool.is_enabled ? "text-emerald-600" : "text-zinc-400"
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${tool.is_enabled ? "bg-emerald-500" : "bg-zinc-300"}`} />
                        {tool.is_enabled ? "Active" : "Disabled"}
                      </span>
                    </div>
                  </div>

                  <button
                    onClick={() => handleToggle(tool)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      tool.is_enabled ? "bg-zinc-900" : "bg-zinc-200"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        tool.is_enabled ? "translate-x-4" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>

                <p className="mt-3 text-xs text-zinc-600 line-clamp-2 leading-relaxed">{tool.description}</p>

                {tool.execution_mode === "server_webhook" && tool.webhook_url && (
                  <div className="mt-3 text-[11px] font-mono text-zinc-500 bg-zinc-50 px-2.5 py-1 rounded-md border border-zinc-200 truncate">
                    {tool.webhook_method} {tool.webhook_url}
                  </div>
                )}
              </div>

              <div className="mt-4 pt-3 border-t border-zinc-100 flex items-center justify-between">
                <span className="text-[11px] text-zinc-400">
                  {Object.keys(tool.parameters_schema?.properties || {}).length} params
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleOpenEditModal(tool)}
                    className="rounded-lg border border-zinc-200 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-50"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(tool)}
                    className="rounded-lg border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-600 shadow-sm transition hover:bg-red-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal Form */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl border border-zinc-200 space-y-5 my-8">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <h3 className="text-base font-bold text-zinc-900">
                {editingTool ? "Edit Custom Tool" : "Create New Custom Tool"}
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-600 transition"
              >
                ✕
              </button>
            </div>

            {formError && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {formError}
              </div>
            )}

            <form onSubmit={handleSubmitForm} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-700 mb-1">
                    Machine Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="get_inventory_stock"
                    className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono text-zinc-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  />
                  <p className="text-[10px] text-zinc-400 mt-1">Alphanumeric, dashes or underscores.</p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-700 mb-1">
                    Display Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Get Inventory Stock"
                    className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-700 mb-1">
                  Tool Description <span className="text-red-500">*</span>
                </label>
                <textarea
                  required
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Fetch live inventory stock count for a given SKU item code from external database."
                  className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-zinc-900"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-700 mb-1">Execution Mode</label>
                <div className="grid grid-cols-2 gap-3">
                  <label
                    className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-xs transition ${
                      executionMode === "client_delegated"
                        ? "border-zinc-900 bg-zinc-900/5 font-semibold text-zinc-900"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600"
                    }`}
                  >
                    <input
                      type="radio"
                      name="execution_mode"
                      value="client_delegated"
                      checked={executionMode === "client_delegated"}
                      onChange={() => setExecutionMode("client_delegated")}
                      className="mt-0.5"
                    />
                    <div>
                      <div>Client Delegated</div>
                      <div className="text-[10px] font-normal text-zinc-500 mt-0.5">
                        Scrutinize returns tool directives to external backend.
                      </div>
                    </div>
                  </label>

                  <label
                    className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-xs transition ${
                      executionMode === "server_webhook"
                        ? "border-zinc-900 bg-zinc-900/5 font-semibold text-zinc-900"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600"
                    }`}
                  >
                    <input
                      type="radio"
                      name="execution_mode"
                      value="server_webhook"
                      checked={executionMode === "server_webhook"}
                      onChange={() => setExecutionMode("server_webhook")}
                      className="mt-0.5"
                    />
                    <div>
                      <div>Server Webhook</div>
                      <div className="text-[10px] font-normal text-zinc-500 mt-0.5">
                        Scrutinize dispatches HTTP webhook directly.
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {executionMode === "server_webhook" && (
                <div className="space-y-3 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
                  <div className="grid grid-cols-4 gap-3">
                    <div className="col-span-3">
                      <label className="block text-xs font-semibold text-zinc-700 mb-1">Webhook URL</label>
                      <input
                        type="url"
                        required
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrl(e.target.value)}
                        placeholder="https://api.myapp.com/webhooks/scrutinize-tools"
                        className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-xs font-mono text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-zinc-700 mb-1">Method</label>
                      <select
                        value={webhookMethod}
                        onChange={(e) => setWebhookMethod(e.target.value)}
                        className="w-full rounded-xl border border-zinc-200 bg-white px-2.5 py-2 text-xs font-mono text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      >
                        <option value="POST">POST</option>
                        <option value="GET">GET</option>
                        <option value="PUT">PUT</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-zinc-700 mb-1">
                      Webhook Headers (JSON format)
                    </label>
                    <textarea
                      rows={2}
                      value={webhookHeadersJson}
                      onChange={(e) => setWebhookHeadersJson(e.target.value)}
                      className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-xs font-mono text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-zinc-700 mb-1">
                  Parameters JSON Schema <span className="text-red-500">*</span>
                </label>
                <textarea
                  required
                  rows={6}
                  value={schemaJson}
                  onChange={(e) => setSchemaJson(e.target.value)}
                  className="w-full rounded-xl border border-zinc-200 bg-zinc-900 p-3 text-xs font-mono text-emerald-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-zinc-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-xl bg-zinc-900 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:opacity-50"
                >
                  {submitting ? "Saving..." : editingTool ? "Save Changes" : "Create Tool"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
