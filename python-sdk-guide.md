# Python编程接口完整示例

## 🐍 Python SDK使用指南

这份指南展示如何通过Python代码与整个知识库系统交互，方便大模型生成改进方案。

---

## 1️⃣ 基础配置与连接

### 方式A：直接调用API

```python
import requests
import json
from typing import List, Dict, Any

class KnowledgeBaseClient:
    """知识库管理系统Python客户端"""
    
    def __init__(self, api_url: str = "http://localhost:8000/api/v1"):
        self.api_url = api_url
        self.session = requests.Session()
        self.token = None
    
    def login(self, username: str, password: str) -> bool:
        """登录并获取token"""
        response = self.session.post(
            f"{self.api_url}/auth/login",
            json={"username": username, "password": password}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    def upload_document(self, file_path: str, file_type: str = "pdf") -> Dict[str, Any]:
        """上传文档"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = self.session.post(
                f"{self.api_url}/documents/upload",
                files=files
            )
        return response.json()
    
    def confirm_document(self, document_id: int) -> Dict[str, Any]:
        """确认文档"""
        response = self.session.post(
            f"{self.api_url}/documents/confirm/{document_id}"
        )
        return response.json()
    
    def get_pending_reviews(self) -> List[Dict[str, Any]]:
        """获取待审核文档"""
        response = self.session.get(
            f"{self.api_url}/review/pending"
        )
        return response.json()["documents"]
    
    def approve_document(self, document_id: int) -> Dict[str, Any]:
        """审核通过"""
        response = self.session.post(
            f"{self.api_url}/review/approve/{document_id}"
        )
        return response.json()
    
    def reject_document(self, document_id: int, reason: str) -> Dict[str, Any]:
        """审核拒绝"""
        response = self.session.post(
            f"{self.api_url}/review/reject/{document_id}",
            json={"reason": reason}
        )
        return response.json()
    
    def query_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
        model: str = "llama2",
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """查询知识库"""
        response = self.session.post(
            f"{self.api_url}/query",
            json={
                "query": query,
                "top_k": top_k,
                "model": model,
                "temperature": temperature
            }
        )
        return response.json()

# 使用示例
if __name__ == "__main__":
    client = KnowledgeBaseClient()
    
    # 登录（管理员账号密码请从 .env 或环境变量读取，不建议写死在代码里）
    import os
    client.login(os.getenv("KB_ADMIN_USERNAME", "admin"), os.environ["KB_ADMIN_PASSWORD"])
    
    # 上传文档
    result = client.upload_document("/path/to/document.pdf")
    document_id = result["document_id"]
    print(f"Document preview: {result['preview']}")
    
    # 确认文档
    client.confirm_document(document_id)
    
    # 查询知识库
    response = client.query_knowledge_base("Python异步编程是什么？")
    print(f"Answer: {response['answer']}")
    print(f"Sources: {response['sources']}")
```

---

## 2️⃣ 本地LangChain集成

### 直接使用LangChain + Ollama

```python
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Milvus
from langchain.llms import Ollama
from langchain.chains import RetrievalQA
from langchain.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pymilvus import connections
import os

class LocalRAGSystem:
    """本地RAG系统"""
    
    def __init__(
        self,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama2"
    ):
        # 初始化向量模型
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"}  # 或 "cuda"
        )
        
        # 初始化LLM
        self.llm = Ollama(
            base_url=ollama_base_url,
            model=ollama_model,
            temperature=0.7
        )
        
        # Milvus配置
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.collection_name = "knowledge_base"
        
        # 连接Milvus
        self._connect_milvus()
    
    def _connect_milvus(self):
        """连接Milvus"""
        connections.connect(
            alias="default",
            host=self.milvus_host,
            port=self.milvus_port
        )
    
    def load_pdf(self, pdf_path: str) -> list:
        """加载PDF文件"""
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        return documents
    
    def load_docx(self, docx_path: str) -> list:
        """加载DOCX文件"""
        loader = Docx2txtLoader(docx_path)
        documents = loader.load()
        return documents
    
    def split_documents(
        self,
        documents: list,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ) -> list:
        """文档分割"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = splitter.split_documents(documents)
        return chunks
    
    def index_documents(self, documents: list, collection_name: str = None):
        """将文档索引到Milvus"""
        if collection_name is None:
            collection_name = self.collection_name
        
        # 创建向量存储
        vector_store = Milvus.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=collection_name,
            connection_args={
                "host": self.milvus_host,
                "port": self.milvus_port
            }
        )
        
        return vector_store
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        collection_name: str = None
    ) -> Dict[str, Any]:
        """查询知识库并生成回答"""
        if collection_name is None:
            collection_name = self.collection_name
        
        # 创建向量存储实例
        vector_store = Milvus(
            embedding_function=self.embeddings,
            collection_name=collection_name,
            connection_args={
                "host": self.milvus_host,
                "port": self.milvus_port
            }
        )
        
        # 创建检索器
        retriever = vector_store.as_retriever(
            search_kwargs={"k": top_k}
        )
        
        # 创建RAG链
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            verbose=True
        )
        
        # 执行查询
        result = qa_chain({"query": query_text})
        
        # 处理结果
        sources = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in result["source_documents"]
        ]
        
        return {
            "query": query_text,
            "answer": result["result"],
            "sources": sources,
            "model": self.llm.model
        }
    
    def batch_index(self, directory: str):
        """批量索引目录中的所有文件"""
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            
            if filename.endswith('.pdf'):
                documents = self.load_pdf(filepath)
            elif filename.endswith('.docx'):
                documents = self.load_docx(filepath)
            else:
                continue
            
            chunks = self.split_documents(documents)
            self.index_documents(chunks)
            print(f"Indexed {filename}: {len(chunks)} chunks")

# 使用示例
if __name__ == "__main__":
    # 初始化系统
    rag = LocalRAGSystem()
    
    # 索引文档
    documents = rag.load_pdf("/path/to/document.pdf")
    chunks = rag.split_documents(documents)
    rag.index_documents(chunks)
    
    # 查询
    result = rag.query("什么是RAG系统？")
    print(f"Answer: {result['answer']}")
    print(f"Sources: {result['sources']}")
```

---

## 3️⃣ 文档处理示例

### 完整的文档解析流程

```python
import PyPDF2
from docx import Document
from typing import List, Tuple
import re

class DocumentParser:
    """文档解析工具"""
    
    @staticmethod
    def parse_pdf(pdf_path: str) -> str:
        """解析PDF文件"""
        text = ""
        try:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page.extract_text()
        except Exception as e:
            print(f"Error parsing PDF: {e}")
        return text
    
    @staticmethod
    def parse_docx(docx_path: str) -> str:
        """解析DOCX文件"""
        doc = Document(docx_path)
        text = ""
        
        for para in doc.paragraphs:
            text += para.text + "\n"
        
        # 提取表格
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text for cell in row.cells])
                text += row_text + "\n"
        
        return text
    
    @staticmethod
    def clean_text(text: str) -> str:
        """清理文本"""
        # 移除多余的空白
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符（保留中文、英文、数字和基本标点）
        text = re.sub(r'[^\u4e00-\u9fff\w\s，。！？；：（）\n]', '', text)
        
        return text.strip()
    
    @staticmethod
    def extract_metadata(file_path: str) -> dict:
        """提取文件元数据"""
        import os
        from datetime import datetime
        
        stat = os.stat(file_path)
        return {
            "filename": os.path.basename(file_path),
            "file_size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "file_type": os.path.splitext(file_path)[1]
        }

class TextSplitter:
    """文本分割工具"""
    
    @staticmethod
    def split_by_sentences(text: str, max_length: int = 512) -> List[str]:
        """按句子分割"""
        # 按句号、问号、感叹号分割
        sentences = re.split(r'[。！？\n]+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if len(current_chunk) + len(sentence) <= max_length:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    @staticmethod
    def split_by_size(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
        """按大小分割（带重叠）"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap
        
        return chunks
    
    @staticmethod
    def split_by_sections(text: str) -> Tuple[List[str], List[str]]:
        """按章节分割"""
        # 匹配章节标题（如 ## 标题、1. 标题等）
        section_pattern = r'^#{1,6}\s+(.+?)$|^\d+\.\s+(.+?)$'
        
        sections = re.split(section_pattern, text, flags=re.MULTILINE)
        
        chunks = []
        headers = []
        
        for i in range(0, len(sections), 3):
            if i + 2 < len(sections):
                header = sections[i + 1] or sections[i + 2]
                content = sections[i + 3] if i + 3 < len(sections) else ""
                
                if content.strip():
                    chunks.append(content.strip())
                    headers.append(header)
        
        return chunks, headers

# 使用示例
if __name__ == "__main__":
    # 解析文档
    parser = DocumentParser()
    
    # PDF处理
    pdf_text = parser.parse_pdf("/path/to/document.pdf")
    clean_text = parser.clean_text(pdf_text)
    
    # 提取元数据
    metadata = parser.extract_metadata("/path/to/document.pdf")
    print(f"Metadata: {metadata}")
    
    # 文本分割
    chunks = TextSplitter.split_by_sentences(clean_text, max_length=512)
    print(f"Chunks count: {len(chunks)}")
    
    # 按章节分割
    sections, headers = TextSplitter.split_by_sections(clean_text)
    for header, section in zip(headers, sections):
        print(f"\n{header}:")
        print(f"{section[:100]}...")
```

---

## 4️⃣ Prompt工程示例

```python
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.llms import Ollama

class PromptManager:
    """提示词管理器"""
    
    # 通用RAG查询提示词
    RAG_PROMPT = """基于以下背景信息，回答用户的问题。如果背景信息中没有相关内容，请明确说明。

背景信息:
{context}

用户问题: {question}

请提供详细、准确的回答，并在适当的地方引用背景信息。"""

    # 内容审核提示词
    REVIEW_PROMPT = """请审查以下文档内容的质量和适当性。

文档内容:
{content}

请从以下方面评估（评分1-10分）:
1. 内容清晰度
2. 信息准确性
3. 专业性
4. 安全性

最后给出审核意见（通过/拒绝）和建议。"""

    # 文本总结提示词
    SUMMARY_PROMPT = """请为以下文本生成简洁的总结（不超过200字）:

{text}

总结:"""

    # 键值提取提示词
    EXTRACTION_PROMPT = """从以下文本中提取关键信息，以JSON格式返回:

{text}

请提取以下字段: {fields}

JSON结果:"""

    @staticmethod
    def create_rag_chain(llm: Ollama):
        """创建RAG查询链"""
        prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=PromptManager.RAG_PROMPT
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        return chain
    
    @staticmethod
    def create_review_chain(llm: Ollama):
        """创建审核链"""
        prompt = PromptTemplate(
            input_variables=["content"],
            template=PromptManager.REVIEW_PROMPT
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        return chain
    
    @staticmethod
    def create_summary_chain(llm: Ollama):
        """创建总结链"""
        prompt = PromptTemplate(
            input_variables=["text"],
            template=PromptManager.SUMMARY_PROMPT
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        return chain
    
    @staticmethod
    def create_extraction_chain(llm: Ollama, fields: str):
        """创建提取链"""
        prompt = PromptTemplate(
            input_variables=["text", "fields"],
            template=PromptManager.EXTRACTION_PROMPT
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        return chain

# 使用示例
if __name__ == "__main__":
    llm = Ollama(
        base_url="http://localhost:11434",
        model="llama2"
    )
    
    # RAG查询
    rag_chain = PromptManager.create_rag_chain(llm)
    result = rag_chain.run(
        context="Python是一种高级编程语言...",
        question="Python适合做什么？"
    )
    print(f"RAG Response: {result}")
    
    # 文本总结
    summary_chain = PromptManager.create_summary_chain(llm)
    summary = summary_chain.run(text="这是一个很长的文本，需要总结...")
    print(f"Summary: {summary}")
    
    # 信息提取
    extraction_chain = PromptManager.create_extraction_chain(
        llm,
        fields="姓名,公司,职位"
    )
    result = extraction_chain.run(
        text="John Smith is a Software Engineer at Google...",
        fields="姓名,公司,职位"
    )
    print(f"Extracted: {result}")
```

---

## 5️⃣ 高级功能示例

### A. 多模型对比

```python
from typing import Dict, List

class MultiModelEvaluator:
    """多模型评估器"""
    
    def __init__(self, models: List[str]):
        self.models = models
        self.llms = {
            model: Ollama(
                base_url="http://localhost:11434",
                model=model,
                temperature=0.7
            )
            for model in models
        }
    
    def compare_responses(self, query: str) -> Dict[str, str]:
        """对比多个模型的回答"""
        results = {}
        
        for model_name, llm in self.llms.items():
            try:
                response = llm.invoke(query)
                results[model_name] = response
            except Exception as e:
                results[model_name] = f"Error: {str(e)}"
        
        return results
    
    def evaluate_quality(self, responses: Dict[str, str]) -> Dict[str, float]:
        """评估回答质量"""
        scores = {}
        
        for model_name, response in responses.items():
            # 简单指标：长度、清晰度等
            score = min(len(response) / 100, 10)  # 示例评分
            scores[model_name] = score
        
        return scores

# 使用
evaluator = MultiModelEvaluator(["llama2", "mistral", "neural-chat"])
responses = evaluator.compare_responses("什么是人工智能？")
scores = evaluator.evaluate_quality(responses)
```

### B. 实时反馈与优化

```python
class FeedbackLoop:
    """反馈循环系统"""
    
    def __init__(self, llm: Ollama):
        self.llm = llm
        self.feedback_history = []
    
    def generate_with_feedback(
        self,
        query: str,
        feedback_required: bool = False
    ) -> Dict[str, Any]:
        """生成回答并收集反馈"""
        
        # 第一次生成
        response = self.llm.invoke(query)
        
        result = {
            "query": query,
            "response": response,
            "version": 1
        }
        
        if feedback_required:
            # 收集用户反馈（模拟）
            feedback = {
                "quality": 7,  # 1-10
                "accuracy": 8,
                "clarity": 6,
                "comments": "需要更多具体例子"
            }
            
            # 基于反馈优化
            improved_response = self._optimize_response(
                response,
                feedback
            )
            
            result["feedback"] = feedback
            result["improved_response"] = improved_response
            result["version"] = 2
        
        self.feedback_history.append(result)
        return result
    
    def _optimize_response(self, response: str, feedback: dict) -> str:
        """基于反馈优化回答"""
        optimization_prompt = f"""
        原始回答:
        {response}
        
        反馈:
        {feedback}
        
        请根据反馈改进回答:
        """
        
        improved = self.llm.invoke(optimization_prompt)
        return improved

# 使用
feedback_loop = FeedbackLoop(llm)
result = feedback_loop.generate_with_feedback("解释什么是递归？", feedback_required=True)
print(f"Version 1: {result['response']}")
print(f"Version 2: {result['improved_response']}")
```

### C. 批量处理与监控

```python
from concurrent.futures import ThreadPoolExecutor
import time

class BatchProcessor:
    """批量处理器"""
    
    def __init__(self, rag_system: LocalRAGSystem, max_workers: int = 5):
        self.rag_system = rag_system
        self.max_workers = max_workers
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "avg_time": 0
        }
    
    def process_queries(self, queries: List[str]) -> List[Dict]:
        """批量处理查询"""
        results = []
        times = []
        
        def process_single(query):
            start = time.time()
            try:
                result = self.rag_system.query(query)
                result["status"] = "success"
                result["processing_time"] = time.time() - start
                times.append(result["processing_time"])
                return result
            except Exception as e:
                return {
                    "query": query,
                    "status": "failed",
                    "error": str(e)
                }
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(process_single, queries))
        
        # 更新统计
        self.stats["total"] = len(queries)
        self.stats["success"] = len([r for r in results if r["status"] == "success"])
        self.stats["failed"] = len([r for r in results if r["status"] == "failed"])
        if times:
            self.stats["avg_time"] = sum(times) / len(times)
        
        return results
    
    def get_stats(self) -> Dict:
        """获取处理统计"""
        return self.stats

# 使用
processor = BatchProcessor(rag_system, max_workers=3)
queries = [
    "什么是Python？",
    "如何学习编程？",
    "机器学习是什么？"
]
results = processor.process_queries(queries)
print(f"Stats: {processor.get_stats()}")
```

---

## 📊 完整工作流示例

```python
async def complete_workflow():
    """完整工作流演示"""
    
    # 1. 初始化系统
    client = KnowledgeBaseClient()
    import os
    client.login(os.getenv("KB_ADMIN_USERNAME", "admin"), os.environ["KB_ADMIN_PASSWORD"])
    
    rag = LocalRAGSystem()
    
    # 2. 上传并处理文档
    print("Step 1: Uploading document...")
    upload_result = client.upload_document("/path/to/document.pdf")
    document_id = upload_result["document_id"]
    
    # 3. 用户确认
    print("Step 2: Confirming document...")
    client.confirm_document(document_id)
    
    # 4. 管理员审核
    print("Step 3: Admin review...")
    pending = client.get_pending_reviews()
    if pending:
        client.approve_document(pending[0]["id"])
    
    # 5. 索引文档
    print("Step 4: Indexing document...")
    parser = DocumentParser()
    text = parser.parse_pdf("/path/to/document.pdf")
    splitter = TextSplitter()
    chunks = splitter.split_by_sentences(text)
    
    # 使用LangChain直接索引
    from langchain.schema import Document
    docs = [Document(page_content=chunk) for chunk in chunks]
    rag.index_documents(docs)
    
    # 6. 查询知识库
    print("Step 5: Querying knowledge base...")
    result = rag.query("文档的主要内容是什么？")
    print(f"Answer: {result['answer']}")
    
    # 7. 批量查询
    print("Step 6: Batch queries...")
    processor = BatchProcessor(rag)
    queries = ["什么是RAG？", "RAG的优点是什么？"]
    batch_results = processor.process_queries(queries)
    print(f"Batch stats: {processor.get_stats()}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(complete_workflow())
```

---

## 🎯 与大模型的交互模式

当你需要大模型改进系统时，可以这样提问：

```python
# 示例：让大模型优化Prompt
improvement_request = """
当前RAG系统查询Prompt:
{current_prompt}

问题: 
- 回答不够准确
- 未能充分引用源文档
- 回答过于冗长

请改进Prompt，使其:
1. 更准确地回答问题
2. 清楚地标注引用
3. 控制回答长度在200字以内

提供改进后的Prompt代码。
"""

# 示例：让大模型添加新功能
feature_request = """
当前系统架构: {system_architecture}

需要新功能:
- 支持自动生成文档摘要
- 支持多语言查询
- 实时性能监控

请为这三个功能：
1. 设计Python类和方法
2. 给出具体实现代码
3. 说明与现有系统的集成方式
"""
```

这样大模型就能理解你的系统，生成可以直接使用或最小化修改就能用的代码。

---

## 📚 常用导入清单

```python
# API客户端
import requests
from requests.auth import HTTPBasicAuth

# LangChain
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Milvus
from langchain.llms import Ollama
from langchain.chains import RetrievalQA, LLMChain
from langchain.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.schema import Document

# Pymilvus
from pymilvus import connections, Collection

# 文档处理
import PyPDF2
from docx import Document as DocxDocument

# 并发处理
from concurrent.futures import ThreadPoolExecutor
import asyncio

# 工具库
import json
import re
import os
from typing import Dict, List, Any, Tuple
from datetime import datetime
```

祝你使用愉快！这份指南包含了所有你需要与大模型沟通的核心编程接口。
