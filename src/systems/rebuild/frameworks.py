"""Real framework retrieval components with scoped, measured Neo4j adapters."""
from .shared import SCHEMA,CYPHER_TEMPLATE


def langchain_retrieve(question,repo,timing,graph,llm):
    from langchain_community.graphs import Neo4jGraph
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
    from langchain_core.language_models.llms import LLM
    from langchain_core.prompts import PromptTemplate
    class Bridge(LLM):
        @property
        def _llm_type(self):return 'shared-one-attempt-gemini'
        def _call(self,prompt,stop=None,run_manager=None,**kwargs):
            return llm.generate(prompt,timing,'retrieval')
    class ScopedNeo4jGraph(Neo4jGraph):
        # The shared backend owns the actual Neo4j driver. Avoid global APOC
        # schema sampling, hidden retries, and unrelated historical labels.
        def __init__(self):
            self.schema=SCHEMA;self.structured_schema={};self._driver=getattr(graph,'driver',None)
        def query(self,query,params=None):return graph.execute(query,repo,timing,params)
        def close(self):pass
        def __del__(self):pass
    store=ScopedNeo4jGraph()
    chain=GraphCypherQAChain.from_llm(llm=Bridge(),graph=store,
        cypher_prompt=PromptTemplate.from_template(CYPHER_TEMPLATE),
        return_direct=True,return_intermediate_steps=True,top_k=100,
        allow_dangerous_requests=True)
    # Explicit schema is the exact same public DL schema used by shared retrieval.
    chain.graph_schema=SCHEMA
    output=chain.invoke({'query':question})
    return output['result'],['langchain:GraphCypherQAChain','langchain:Neo4jGraph:scoped'],output['intermediate_steps']


def llamaindex_retrieve(question,repo,timing,graph,llm):
    from llama_index.core.indices.property_graph import TextToCypherRetriever
    from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
    from llama_index.core.llms import CustomLLM,CompletionResponse,LLMMetadata
    from llama_index.core.llms.callbacks import llm_completion_callback
    class Bridge(CustomLLM):
        @property
        def metadata(self):return LLMMetadata(context_window=32768,num_output=1024,model_name=llm.model)
        @llm_completion_callback()
        def complete(self,prompt,formatted=False,**kwargs):
            return CompletionResponse(text=llm.generate(prompt,timing,'retrieval'))
        @llm_completion_callback()
        def stream_complete(self,prompt,formatted=False,**kwargs):
            yield self.complete(prompt,formatted,**kwargs)
    class ScopedPropertyGraphStore(Neo4jPropertyGraphStore):
        # Do not create LlamaIndex-specific indexes or sample other datasets.
        def __init__(self):
            self._driver=getattr(graph,'driver',None);self.structured_schema={}
        def get_schema_str(self,refresh=False):return SCHEMA
        def structured_query(self,query,param_map=None):return graph.execute(query,repo,timing,param_map)
        def close(self):pass
        def __del__(self):pass
    retriever=TextToCypherRetriever(graph_store=ScopedPropertyGraphStore(),llm=Bridge(),
        text_to_cypher_template=CYPHER_TEMPLATE,include_raw_response_as_metadata=True,
        summarize_response=False)
    result=retriever.retrieve(question)
    rows=[r for node in result for r in node.metadata['response']]
    return rows,['llamaindex:TextToCypherRetriever','llamaindex:Neo4jPropertyGraphStore:scoped'],[node.metadata['query'] for node in result]
