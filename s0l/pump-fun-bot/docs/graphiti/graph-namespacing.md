# Graph Namespacing

> Using group_ids to create isolated graph namespaces

## Overview

Graphiti supports the concept of graph namespacing through the use of `group_id` parameters. This feature allows you to create isolated graph environments within the same Graphiti instance, enabling multiple distinct knowledge graphs to coexist without interference.

Graph namespacing is particularly useful for:

* **Multi-tenant applications**: Isolate data between different customers or organizations
* **Testing environments**: Maintain separate development, testing, and production graphs
* **Domain-specific knowledge**: Create specialized graphs for different domains or use cases
* **Team collaboration**: Allow different teams to work with their own graph spaces

## How Namespacing Works

In Graphiti, every node and edge can be associated with a `group_id`. When you specify a `group_id`, you're effectively creating a namespace for that data. Nodes and edges with the same `group_id` form a cohesive, isolated graph that can be queried and manipulated independently from other namespaces.

### Key Benefits

* **Data isolation**: Prevent data leakage between different namespaces
* **Simplified management**: Organize and manage related data together
* **Performance optimization**: Improve query performance by limiting the search space
* **Flexible architecture**: Support multiple use cases within a single Graphiti instance

## Using group\_ids in Graphiti

### Adding Episodes with group\_id

When adding episodes to your graph, you can specify a `group_id` to namespace the episode and all its extracted entities:

```python
await graphiti.add_episode(
    name="customer_interaction",
    episode_body="Customer Jane mentioned she loves our new SuperLight Wool Runners in Dark Grey.",
    source=EpisodeType.text,
    source_description="Customer feedback",
    reference_time=datetime.now(),
    group_id="customer_team"  # This namespaces the episode and its entities
)
```

### Adding Fact Triples with group\_id

When manually adding fact triples, ensure both nodes and the edge share the same `group_id`:

```python
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge
import uuid
from datetime import datetime

# Define a namespace for this data
namespace = "product_catalog"

# Create source and target nodes with the namespace
source_node = EntityNode(
    uuid=str(uuid.uuid4()),
    name="SuperLight Wool Runners",
    group_id=namespace  # Apply namespace to source node
)

target_node = EntityNode(
    uuid=str(uuid.uuid4()),
    name="Sustainable Footwear",
    group_id=namespace  # Apply namespace to target node
)

# Create an edge with the same namespace
edge = EntityEdge(
    group_id=namespace,  # Apply namespace to edge
    source_node_uuid=source_node.uuid,
    target_node_uuid=target_node.uuid,
    created_at=datetime.now(),
    name="is_category_of",
    fact="SuperLight Wool Runners is a product in the Sustainable Footwear category"
)

# Add the triplet to the graph
await graphiti.add_triplet(source_node, edge, target_node)
```

### Querying Within a Namespace

When querying the graph, specify the `group_id` to limit results to a particular namespace:

```python
# Search within a specific namespace
search_results = await graphiti.search(
    query="Wool Runners",
    group_id="product_catalog"  # Only search within this namespace
)

# For more advanced node-specific searches, use the _search method with a recipe
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF

# Create a search config for nodes only
node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
node_search_config.limit = 5  # Limit to 5 results

# Execute the node search within a specific namespace
node_search_results = await graphiti._search(
    query="SuperLight Wool Runners",
    group_id="product_catalog",  # Only search within this namespace
    config=node_search_config
)
```

## Best Practices for Graph Namespacing

1. **Consistent naming**: Use a consistent naming convention for your `group_id` values
2. **Documentation**: Maintain documentation of your namespace structure and purpose
3. **Granularity**: Choose an appropriate level of granularity for your namespaces
   * Too many namespaces can lead to fragmented data
   * Too few namespaces may not provide sufficient isolation
4. **Cross-namespace queries**: When necessary, perform multiple queries across namespaces and combine results in your application logic

## Example: Multi-tenant Application

Here's an example of using namespacing in a multi-tenant application:

```python
async def add_customer_data(tenant_id, customer_data):
    """Add customer data to a tenant-specific namespace"""
    
    # Use the tenant_id as the namespace
    namespace = f"tenant_{tenant_id}"
    
    # Create an episode for this customer data
    await graphiti.add_episode(
        name=f"customer_data_{customer_data['id']}",
        episode_body=customer_data,
        source=EpisodeType.json,
        source_description="Customer profile update",
        reference_time=datetime.now(),
        group_id=namespace  # Namespace by tenant
    )

async def search_tenant_data(tenant_id, query):
    """Search within a tenant's namespace"""
    
    namespace = f"tenant_{tenant_id}"
    
    # Only search within this tenant's namespace
    return await graphiti.search(
        query=query,
        group_id=namespace
    )
```
