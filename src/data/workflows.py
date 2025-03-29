from typing import Any, Sequence

from pydantic import BaseModel


class WorkflowInput(BaseModel):
    """
    Represents a workflow input.
    """
    node_id: str
    value: Any
    node_type: str | None = None
    display_name: str | None = None
    description: str | None = None


class WorkflowWebsocketImageOutput(BaseModel):
    """
    Represents a workflow output.
    """
    node_id: str
    node_type: str
    connection_id: str
    output_id: str



class WorkflowDescriptor(BaseModel):
    """
    Represents a workflow descriptor
    """
    workflow_id: str
    workflow_json: dict[str, Any]
    nodes: dict[str, Any]
    edges: Sequence[dict[str, Any]]
    source_ids: Sequence[str]
    sink_ids: Sequence[str]
    external_parameters: dict[str, dict[str, Any]]
    inputs: Sequence[WorkflowInput]
    outputs: Sequence[WorkflowWebsocketImageOutput]