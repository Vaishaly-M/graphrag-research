"""Fixed question-only features. No benchmark labels, H data or gold queries."""
import re
import numpy as np
from src.systems.rebuild.shared import template

GRAPH_WORDS=('commit','issue','pull request','author','developer','contributor','directory','path','count','list','dependency','modified','assigned','merged')
VECTOR_WORDS=('explain','describe','documentation','readme','implementation','function','method','class','snippet','meaning','behavior','code')
MULTI_WORDS=('through','across','between','related','impact','affected','transitive','chain','indirect','both')
NAMES=('template_match','graph_keywords','vector_keywords','multi_hop_keywords','mixed_sources',
       'sha','issue_number','file_path','email','quoted_text','who','where','how','why','what','list','count','word_count')


def question_text(question,repo):
    return re.sub(r'\s+',' ',question.replace(repo,'<repository>')).strip()


def features(question,repo):
    text=question_text(question,repo);lower=text.casefold()
    def matches(words):return sum(bool(re.search(r'\b'+re.escape(w)+r'\b',lower)) for w in words)
    graph,vector,multi=matches(GRAPH_WORDS),matches(VECTOR_WORDS),matches(MULTI_WORDS)
    values=[bool(template(text)),graph,vector,multi,bool(graph and vector),
        bool(re.search(r'\b[0-9a-f]{7,40}\b',lower)),bool(re.search(r'(?:#|\bissue\s+|\bpr\s+)\d+',lower)),
        bool(re.search(r'(?:[\w.-]+[/\\])+[\w.-]*|\b[\w-]+\.(?:py|java|js|ts|md|xml|yaml|yml|json)\b',text)),
        bool(re.search(r'[\w.+-]+@[\w.-]+',text)),bool(re.search(r'''["'][^"']+["']''',text))]
    values.extend(bool(re.search(r'\b'+word+r'\b',lower)) for word in ('who','where','how','why','what','list','count'))
    values.append(min(len(text.split()),100)/100)
    return dict(zip(NAMES,map(float,values)))


def matrix(questions,encoder):
    texts=[question_text(q['question'],q['repo']) for q in questions]
    embeddings=np.asarray(encoder.encode(texts),dtype=float)
    embeddings/=np.maximum(np.linalg.norm(embeddings,axis=1,keepdims=True),1e-12)
    explicit=np.array([[features(q['question'],q['repo'])[k] for k in NAMES] for q in questions])
    return np.concatenate([explicit,embeddings],axis=1)
