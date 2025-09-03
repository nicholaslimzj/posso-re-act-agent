"""
FAQ Tool - Local embeddings with sentence-transformers
"""
from typing import Dict, List, Any, Tuple
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

# Try to import sentence-transformers, fall back if not available
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    logger.warning("sentence-transformers not available, will use text-based search")
    EMBEDDINGS_AVAILABLE = False

class FAQTool:
    def __init__(self, faq_file_path: str = "data/posso_faq.txt"):
        self.faq_file_path = faq_file_path
        self.chunks = []
        self.chunk_metadata = []
        self.chunk_embeddings = None
        self.embeddings_model = None
        
        self._initialize()
    
    def _initialize(self):
        """Initialize the FAQ tool with embeddings if available"""
        try:
            # Load FAQ content first
            self._load_faq_content()
            
            # Try to initialize embeddings
            if EMBEDDINGS_AVAILABLE:
                try:
                    logger.info("Initializing sentence-transformers model (may download on first use)...")
                    # Use a small, efficient model
                    self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')
                    
                    # Compute embeddings for all chunks
                    self._compute_embeddings()
                    logger.info(f"✅ FAQ tool initialized with {len(self.chunks)} chunks and LOCAL EMBEDDINGS")
                except Exception as e:
                    logger.warning(f"Failed to initialize embeddings: {e}")
                    logger.info("Falling back to text-based search")
                    self.embeddings_model = None
                    self.chunk_embeddings = None
            else:
                logger.info("FAQ tool initialized with text-based search (no embeddings)")
            
        except Exception as e:
            logger.error(f"Failed to initialize FAQ tool: {e}")
            self.chunk_embeddings = None
    
    def _load_faq_content(self):
        """Load and chunk the FAQ content"""
        try:
            with open(self.faq_file_path, 'r', encoding='utf-8') as f:
                faq_content = f.read()
            
            # Split content into Q&A pairs
            text_splitter = RecursiveCharacterTextSplitter(
                separators=["\n\n", "\n", "?", "."],
                chunk_size=500,
                chunk_overlap=50,
                length_function=len
            )
            
            self.chunks = text_splitter.split_text(faq_content)
            
            # Create metadata for each chunk
            for i, chunk in enumerate(self.chunks):
                # Extract question if possible
                lines = chunk.strip().split('\n')
                question = lines[0] if lines and '?' in lines[0] else f"FAQ Chunk {i+1}"
                
                self.chunk_metadata.append({
                    "chunk_id": i,
                    "question": question,
                    "content": chunk.strip()
                })
            
            logger.debug(f"Created {len(self.chunks)} FAQ chunks")
            
        except Exception as e:
            logger.error(f"Failed to load FAQ content: {e}")
            raise
    
    def _compute_embeddings(self):
        """Compute embeddings for all FAQ chunks using local model"""
        if not self.embeddings_model:
            return
            
        try:
            # Prepare texts for embedding
            texts_to_embed = [chunk["content"] for chunk in self.chunk_metadata]
            
            # Compute embeddings using sentence-transformers
            logger.debug("Computing embeddings for FAQ chunks...")
            embeddings_list = self.embeddings_model.encode(
                texts_to_embed,
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            # Store as numpy array
            self.chunk_embeddings = embeddings_list
            logger.debug(f"Computed embeddings with shape: {self.chunk_embeddings.shape}")
            
        except Exception as e:
            logger.error(f"Failed to compute embeddings: {e}")
            self.chunk_embeddings = None
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        # Normalize vectors
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)
        
        # Compute dot product
        return np.dot(vec1_norm, vec2_norm)
    
    def _semantic_search(self, question: str, top_k: int = 3) -> List[Tuple[int, float]]:
        """Perform semantic search using embeddings"""
        if not self.embeddings_model or self.chunk_embeddings is None:
            return []
            
        try:
            # Embed the question
            question_embedding = self.embeddings_model.encode(
                question,
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            # Compute similarities with all chunks
            similarities = []
            for i, chunk_vec in enumerate(self.chunk_embeddings):
                similarity = self._cosine_similarity(question_embedding, chunk_vec)
                similarities.append((i, float(similarity)))
            
            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Return top-k results
            return similarities[:top_k]
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    def _text_search(self, question: str, top_k: int = 3) -> List[Tuple[int, float]]:
        """Text-based search using keyword matching"""
        question_lower = question.lower()
        similarities = []
        
        # Important keywords to boost
        boost_words = {'school', 'tour', 'hours', 'admission', 'curriculum', 
                      'age', 'grade', 'fees', 'uniform', 'meals', 'transport'}
        
        for i, chunk_meta in enumerate(self.chunk_metadata):
            chunk_content = chunk_meta["content"].lower()
            
            # Calculate similarity based on word overlap
            question_words = set(question_lower.split())
            content_words = set(chunk_content.split())
            
            # Filter to meaningful words (length > 3)
            question_words = {w.strip('.,!?') for w in question_words if len(w) > 3}
            
            # Calculate base similarity
            common_words = question_words.intersection(content_words)
            similarity = len(common_words) / max(len(question_words), 1)
            
            # Boost if contains important keywords
            boost = sum(0.1 for word in boost_words if word in chunk_content)
            similarity = min(1.0, similarity + boost)
            
            if similarity > 0.1:
                similarities.append((i, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def get_faq_answer(self, question: str, top_k: int = 3, similarity_threshold: float = 0.4) -> Dict[str, Any]:
        """
        Retrieve FAQ answer using semantic search with embeddings or text search.
        
        Args:
            question: The user's question
            top_k: Number of similar chunks to retrieve
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            Dict with answer and related topics, or no_match status
        """
        try:
            if not self.chunks:
                return {"status": "error", "message": "FAQ tool not initialized"}
            
            # Use embeddings if available, otherwise text search
            if self.chunk_embeddings is not None:
                logger.debug(f"Using vector search for: '{question[:50]}...'")
                search_results = self._semantic_search(question, top_k)
            else:
                logger.debug(f"Using text search for: '{question[:50]}...'")
                search_results = self._text_search(question, top_k)
            
            if not search_results:
                return {"status": "no_match"}
            
            # Filter by similarity threshold and collect relevant chunks
            relevant_chunks = []
            for chunk_idx, similarity in search_results:
                if similarity >= similarity_threshold:
                    chunk_meta = self.chunk_metadata[chunk_idx]
                    relevant_chunks.append({
                        "content": chunk_meta["content"],
                        "question": chunk_meta["question"],
                        "similarity": similarity
                    })
            
            if not relevant_chunks:
                # If no chunks meet threshold but best match is decent, use it
                if search_results and search_results[0][1] > 0.25:
                    chunk_idx, similarity = search_results[0]
                    chunk_meta = self.chunk_metadata[chunk_idx]
                    relevant_chunks = [{
                        "content": chunk_meta["content"],
                        "question": chunk_meta["question"],
                        "similarity": similarity
                    }]
                else:
                    return {"status": "no_match"}
            
            # Combine relevant chunks into a comprehensive answer
            answer_parts = []
            related_topics = []
            
            for chunk in relevant_chunks:
                answer_parts.append(chunk["content"])
                if chunk["question"] not in related_topics:
                    related_topics.append(chunk["question"])
            
            combined_answer = "\n\n".join(answer_parts)
            
            return {
                "status": "success",
                "answer": combined_answer,
                "related_topics": related_topics[:3],
                "similarity_scores": [chunk["similarity"] for chunk in relevant_chunks]
            }
            
        except Exception as e:
            logger.error(f"Error retrieving FAQ answer: {e}")
            return {"status": "error", "message": str(e)}

# Global instance
faq_tool = FAQTool()

def get_faq_answer(question: str) -> dict:
    """
    Retrieve FAQ answer for school/tour related questions.
    Returns: {"answer": "...", "related_topics": [...]} or {"status": "no_match"}
    """
    return faq_tool.get_faq_answer(question)