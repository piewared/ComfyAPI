import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, Sequence

import aiohttp
from pydantic import BaseModel

from src.config import get_comfyui_settings
from src.data.workflows import WorkflowDescriptor, WorkflowInput, WorkflowWebsocketImageOutput
from src.utils.introspection import get_absolute_path


@lru_cache(maxsize=20)
def analyze_workflow(workflow_id: str, workflow_path: Path) -> WorkflowDescriptor:
    """
    Performs graph analysis on a single workflow (dictionary of node definitions).
    Returns an analysis dict containing:
      - nodes: the original node definitions.
      - edges: a list of edges (each as { "from", "to", "parameter" }).
      - sources: list of node ids with no incoming edges.
      - sinks: list of node ids with no outgoing edges.
      - external_parameters: a mapping of node_id to a dict of parameters provided as literals.
    """
    # Lookup the workflow by id.
    workflow = load_workflow(workflow_path)

    # There are two kinds of workflow definitions in ComfyUI: UI and API JSON files. We want only the API definitions.
    # So we will filter out the UI definitions by looking for a top level 'nodes' key, which does not exist in API definitions.
    if 'nodes' in workflow:
        raise ValueError(f"Workflow {workflow_id} is not a valid API workflow definition.")

    nodes_by_id = {n_id: n for n_id, n in workflow.items() if 'class_type' in n}
    edges = []
    # Initialize counters for incoming and outgoing edges.
    incoming = {node_id: 0 for node_id in nodes_by_id}
    outgoing = {node_id: 0 for node_id in nodes_by_id}

    # Build the edge list by iterating over every node’s inputs.
    for node_id, node in nodes_by_id.items():
        inputs = node.get("inputs", {})
        for param, value in inputs.items():
            if isinstance(value, list) and len(value) >= 1 and isinstance(value[0], str):
                source_node = value[0]
                edges.append({"from": source_node, "to": node_id, "parameter": param})
                # Increase counters only if the referenced node exists.
                if source_node in incoming:
                    incoming[node_id] += 1
                    outgoing[source_node] += 1

    # Sources are nodes that have defined inputs but no incoming edges.
    sources = [node_id for node_id, count in incoming.items() if
               count == 0 and nodes_by_id[node_id]['inputs']]
    sinks = [node_id for node_id, count in outgoing.items() if count == 0]

    # For external parameters: any input value that is not a reference is assumed to be externally set.
    external_parameters = {}
    for node_id, node in nodes_by_id.items():
        inputs = node.get("inputs", {})
        ext_params = {}
        for param, value in inputs.items():
            # If not a reference, add it as an external parameter.
            if not (isinstance(value, list) and len(value) > 0 and isinstance(value[0], str)):
                ext_params[param] = value
        if ext_params:
            external_parameters[node_id] = ext_params

    # Get ComfyUI deploy input nodes
    input_nodes = {n_id: n for n_id, n in nodes_by_id.items() if n["class_type"].startswith("ComfyUIDeployExternal")}
    output_nodes = {n_id: n for n_id, n in nodes_by_id.items() if
                    n["class_type"].startswith("ComfyDeployWebscoketImageOutput") or
                    n["class_type"].startswith("ComfyDeployWebsocketImageOutput") or
                    n["class_type"].startswith("ComfyUIDeployWebscoketImageOutput") or
                    n["class_type"].startswith("ComfyUIDeployWebsocketImageOutput")
                    }

    return WorkflowDescriptor(workflow_id=workflow_id, nodes=nodes_by_id, edges=edges, source_ids=sources,
                              sink_ids=sinks, workflow_json=workflow,
                              external_parameters=external_parameters,
                              inputs=[WorkflowInput(node_id=in_node_id, node_type=in_node['class_type'],
                                                    value=in_node['inputs']['input_id'],
                                                    display_name=in_node['inputs']['display_name'],
                                                    description=in_node['inputs']['description']) for
                                      in_node_id, in_node in input_nodes.items()],
                              outputs=[WorkflowWebsocketImageOutput(node_id=out_node_id, node_type=out_node['class_type'],
                                                      connection_id='', output_id='') for
                                       out_node_id, out_node in output_nodes.items()]
                              )

@ lru_cache(maxsize=1)
def get_workflows() -> dict[str, Path]:
    """
    Returns a dict of workflow ids to paths
    """

    # Get the absolute path to the workflows directory in the ComfyUI settings.
    comfyui_workflows_path = get_comfyui_settings().workflows_path

    # Get the absolute path to the workflows directory in the project directory tree
    additional_workflows_path = get_absolute_path("workflows")

    # Combine the two paths
    workflows_path = [comfyui_workflows_path, additional_workflows_path]

    # Iterate through all workflow paths and extract the workflow files
    workflow_files = {}
    for workflow_dir in workflows_path:
        # Combine files in all paths into a single dictionary. Note that if there are duplicate keys, the last one will be used.
        try:
            workflow_files.update({f.stem:f for f in workflow_dir.iterdir() if f.is_file() and f.suffix == ".json"})
        except FileNotFoundError:
            # If the directory doesn't exist, skip it.
            continue
        except PermissionError:
            # If there are permission issues, skip it.
            continue
        except OSError:
            # If there are other OS errors, skip it.
            continue

    # Analyze each workflow file.
    valid_workflows = {}
    for wf_id, wf_path in workflow_files.items():
        # Get the workflow descriptor.
        try:
            wf_desc = analyze_workflow(wf_id, wf_path)
        except ValueError:
            continue

        # If the descriptor has at least one input, consider it valid
        if len(wf_desc.inputs) > 0:
            valid_workflows[wf_id] = wf_path

    # Return the valid workflows
    return valid_workflows

@lru_cache(maxsize=10)
def load_workflow(workflow_path: Path) -> Dict[str, Any]:
    """
    Load the workflow definition from a JSON file.
    Assumes the top-level workflows directory contains one or more workflow API files.
    """

    with open(workflow_path, "r") as f:
        workflow = json.load(f)

    return workflow

def get_workflow_path_by_id(workflow_id: str) -> Path:
    """
    Get the path to a workflow by its ID.
    """
    workflows = get_workflows()
    return workflows[workflow_id]

if __name__ == "__main__":
    m_workflows = get_workflows()
    desc = analyze_workflow(next(iter(m_workflows.values())))

    desc.inputs[
        0].value = 'https://www.thecarycompany.com/media/catalog/product/7/5/750-ml-emerald-green-champagne-bottle.jpg'

