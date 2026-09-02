-- Migration: 023_project_tools.sql
-- Create project_tools table for dynamic, project-scoped custom tools.

CREATE TABLE IF NOT EXISTS project_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    execution_mode VARCHAR(32) NOT NULL DEFAULT 'client_delegated',
    webhook_url TEXT NULL,
    webhook_method VARCHAR(10) NULL DEFAULT 'POST',
    webhook_headers JSONB NULL DEFAULT '{}'::jsonb,
    parameters_schema JSONB NOT NULL DEFAULT '{
        "type": "object",
        "properties": {},
        "required": []
    }'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_project_tool_name UNIQUE (project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_project_tools_project ON project_tools(project_id) WHERE is_enabled = TRUE;
