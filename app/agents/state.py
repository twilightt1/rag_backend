from typing import TypedDict


class AgentState(TypedDict):
           
    user_id:         str
    conversation_id: str
    query:           str
    rewritten_query: str                                     

            
    query_type:      str                                                        
    router_confidence: float                                    
    router_reasoning:  str                                            
    search_variants:   list[str]                                    

            
    history:         list[dict]                                                     

                                                       
    bm25_results:    list[dict]
    vector_results:  list[dict]
    fused_chunks:    list[dict]                        

                                                      
    reranked_chunks: list[dict]                                          

            
    response:        str
    token_count:     int
    agent_trace:     dict                                           

             
    error:           str | None
    should_stream:   bool
    has_documents:   bool                                          
    document_count:  int

                                  
    context_relevant: bool
    is_hallucination: bool
    answers_question: bool
    retry_count:      int
