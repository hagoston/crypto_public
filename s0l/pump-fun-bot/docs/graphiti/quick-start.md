# Quick Start

> Getting started with Graphiti

<Info>
  For complete working examples, check out the [Graphiti Quickstart Examples](https://github.com/getzep/graphiti/tree/main/examples/quickstart) on GitHub.
</Info>

## Installation

Requirements:

* Python 3.10 or higher
* Neo4j 5.26 or higher or FalkorDB 1.1.2 or higher (see [Graph Database Configuration](graph-database-configuration) for setup options)
* OpenAI API key (Graphiti defaults to OpenAI for LLM inference and embedding)

<Note>
  The simplest way to install Neo4j is via [Neo4j Desktop](https://neo4j.com/download/). It provides a user-friendly interface to manage Neo4j instances and databases.
</Note>

```bash
pip install graphiti-core
```

or

```bash
uv add graphiti-core
```

### Alternative LLM Providers

<Note>
  While Graphiti defaults to OpenAI, it supports multiple LLM providers including Azure OpenAI, Google Gemini, Anthropic, Groq, and local models via Ollama. For detailed configuration instructions, see our [LLM Configuration](llm-configuration) guide.
</Note>

### Environment Variables

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=your_openai_api_key_here
```

#### Optional Variables

* `USE_PARALLEL_RUNTIME`: Enable Neo4j's parallel runtime feature for search queries (not supported in Community Edition)
* `GRAPHITI_TELEMETRY_ENABLED`: Set to `false` to disable anonymous telemetry collection

## Getting Started with Graphiti

For a comprehensive overview of Graphiti and its capabilities, check out the [Overview](overview) page.

### Required Imports

First, import the necessary libraries for working with Graphiti:

```python
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from logging import INFO

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
```

### Configuration

<Note>
  Graphiti uses OpenAI by default for LLM inference and embedding. Ensure that an `OPENAI_API_KEY` is set in your environment. Support for multiple LLM providers is available - see our [LLM Configuration](llm-configuration) guide.

  Graphiti also requires Neo4j connection parameters. Set the following environment variables:

  * `NEO4J_URI`: The URI of your Neo4j database (default: bolt://localhost:7687)
  * `NEO4J_USER`: Your Neo4j username (default: neo4j)
  * `NEO4J_PASSWORD`: Your Neo4j password

  For detailed database setup instructions, see our [Graph Database Configuration](graph-database-configuration) guide.
</Note>

Set up logging and environment variables for connecting to the Neo4j database:

```python
# Configure logging
logging.basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

load_dotenv()

# Neo4j connection parameters
# Make sure Neo4j Desktop is running with a local DBMS started
neo4j_uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
neo4j_user = os.environ.get('NEO4J_USER', 'neo4j')
neo4j_password = os.environ.get('NEO4J_PASSWORD', 'password')

if not neo4j_uri or not neo4j_user or not neo4j_password:
    raise ValueError('NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set')
```

### Main Function

Create an async main function to run all Graphiti operations:

```python
async def main():
    # Main function implementation will go here
    pass

if __name__ == '__main__':
    asyncio.run(main())
```

### Initialization

Connect to Neo4j and set up Graphiti indices. This is required before using other Graphiti functionality:

```python
# Initialize Graphiti with Neo4j connection
graphiti = Graphiti(neo4j_uri, neo4j_user, neo4j_password)

try:
    # Initialize the graph database with graphiti's indices. This only needs to be done once.
    await graphiti.build_indices_and_constraints()
    
    # Additional code will go here
    
finally:
    # Close the connection
    await graphiti.close()
    print('\nConnection closed')
```

### Adding Episodes

Episodes are the primary units of information in Graphiti. They can be text or structured JSON and are automatically processed to extract entities and relationships. For more detailed information on episodes and bulk loading, see the [Adding Episodes](adding-episodes) page:

```python
# Episodes list containing both text and JSON episodes
episodes = [
    {
        'content': 'Kamala Harris is the Attorney General of California. She was previously '
        'the district attorney for San Francisco.',
        'type': EpisodeType.text,
        'description': 'podcast transcript',
    },
    {
        'content': 'As AG, Harris was in office from January 3, 2011 – January 3, 2017',
        'type': EpisodeType.text,
        'description': 'podcast transcript',
    },
    {
        'content': {
            'name': 'Gavin Newsom',
            'position': 'Governor',
            'state': 'California',
            'previous_role': 'Lieutenant Governor',
            'previous_location': 'San Francisco',
        },
        'type': EpisodeType.json,
        'description': 'podcast metadata',
    },
    {
        'content': {
            'name': 'Gavin Newsom',
            'position': 'Governor',
            'term_start': 'January 7, 2019',
            'term_end': 'Present',
        },
        'type': EpisodeType.json,
        'description': 'podcast metadata',
    },
]

# Add episodes to the graph
for i, episode in enumerate(episodes):
    await graphiti.add_episode(
        name=f'Freakonomics Radio {i}',
        episode_body=episode['content']
        if isinstance(episode['content'], str)
        else json.dumps(episode['content']),
        source=episode['type'],
        source_description=episode['description'],
        reference_time=datetime.now(timezone.utc),
    )
    print(f'Added episode: Freakonomics Radio {i} ({episode["type"].value})')
```

### Basic Search

The simplest way to retrieve relationships (edges) from Graphiti is using the search method, which performs a hybrid search combining semantic similarity and BM25 text retrieval. For more details on search capabilities, see the [Searching the Graph](searching) page:

```python
# Perform a hybrid search combining semantic similarity and BM25 retrieval
print("\nSearching for: 'Who was the California Attorney General?'")
results = await graphiti.search('Who was the California Attorney General?')

# Print search results
print('\nSearch Results:')
for result in results:
    print(f'UUID: {result.uuid}')
    print(f'Fact: {result.fact}')
    if hasattr(result, 'valid_at') and result.valid_at:
        print(f'Valid from: {result.valid_at}')
    if hasattr(result, 'invalid_at') and result.invalid_at:
        print(f'Valid until: {result.invalid_at}')
    print('---')
```

### Center Node Search

For more contextually relevant results, you can use a center node to rerank search results based on their graph distance to a specific node. This is particularly useful for entity-specific queries as described in the [Searching the Graph](searching) page:

```python
# Use the top search result's UUID as the center node for reranking
if results and len(results) > 0:
    # Get the source node UUID from the top result
    center_node_uuid = results[0].source_node_uuid

    print('\nReranking search results based on graph distance:')
    print(f'Using center node UUID: {center_node_uuid}')

    reranked_results = await graphiti.search(
        'Who was the California Attorney General?', center_node_uuid=center_node_uuid
    )

    # Print reranked search results
    print('\nReranked Search Results:')
    for result in reranked_results:
        print(f'UUID: {result.uuid}')
        print(f'Fact: {result.fact}')
        if hasattr(result, 'valid_at') and result.valid_at:
            print(f'Valid from: {result.valid_at}')
        if hasattr(result, 'invalid_at') and result.invalid_at:
            print(f'Valid until: {result.invalid_at}')
        print('---')
else:
    print('No results found in the initial search to use as center node.')
```

### Node Search Using Search Recipes

Graphiti provides predefined search recipes optimized for different search scenarios. Here we use NODE\_HYBRID\_SEARCH\_RRF for retrieving nodes directly instead of edges. For a complete list of available search recipes and reranking approaches, see the [Configurable Search Strategies](searching#configurable-search-strategies) section in the Searching documentation:

```python
# Example: Perform a node search using _search method with standard recipes
print(
    '\nPerforming node search using _search method with standard recipe NODE_HYBRID_SEARCH_RRF:'
)

# Use a predefined search configuration recipe and modify its limit
node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
node_search_config.limit = 5  # Limit to 5 results

# Execute the node search
node_search_results = await graphiti._search(
    query='California Governor',
    config=node_search_config,
)

# Print node search results
print('\nNode Search Results:')
for node in node_search_results.nodes:
    print(f'Node UUID: {node.uuid}')
    print(f'Node Name: {node.name}')
    node_summary = node.summary[:100] + '...' if len(node.summary) > 100 else node.summary
    print(f'Content Summary: {node_summary}')
    print(f"Node Labels: {', '.join(node.labels)}")
    print(f'Created At: {node.created_at}')
    if hasattr(node, 'attributes') and node.attributes:
        print('Attributes:')
        for key, value in node.attributes.items():
            print(f'  {key}: {value}')
    print('---')
```

### Complete Example

For a complete working example that puts all these concepts together, check out the [Graphiti Quickstart Examples](https://github.com/getzep/graphiti/tree/main/examples/quickstart) on GitHub.

## Next Steps

Now that you've learned the basics of Graphiti, you can explore more advanced features:

* [Custom Entity Types](custom-entity-types): Learn how to define and use custom entity types to better model your domain-specific knowledge
* [Communities](communities): Discover how to work with communities, which are groups of related nodes that share common attributes or relationships
* [Advanced Search Techniques](searching): Explore more sophisticated search strategies, including different reranking approaches and configurable search recipes
* [Adding Fact Triples](adding-fact-triples): Learn how to directly add fact triples to your graph for more precise knowledge representation
* [Agent Integration](agent): Discover how to integrate Graphiti with LLM agents for more powerful AI applications

<Info>
  Make sure to run await statements within an [async function](https://docs.python.org/3/library/asyncio-task.html).
</Info>
