import numpy as np
import ollama as ollm
import chromadb as cdb
import chromadb.errors as cdberr
try:
    from src.database import *
except ModuleNotFoundError:
    from database import *
from typing import Mapping, TYPE_CHECKING
if TYPE_CHECKING:
    from database import *

chroma = cdb.PersistentClient()
products = chroma.get_or_create_collection("products", embedding_function=OllamaEmbedder())

def decomposeTags(original: Mapping[str, object]):
    of = dict(original)
    if "tags" in of and isinstance(of["tags"], str):
        of["tags"] = of["tags"].split(";")
    return of

def embed(query: str) -> np.ndarray:
    vectors = ollm.embed("embeddinggemma", query).embeddings
    return np.array(vectors[0], dtype=np.float32)

def embeddingDistance(first: np.ndarray, second: str) -> float:
    return np.sum(np.square(np.subtract(first, embed(second))))

emptyEmbeddings = {"metadatas": [[]], "distances": [[]]}
def search(query: str, exactOnly: bool) -> list[ProductData]:
    try:
        embeddingMatches = emptyEmbeddings if exactOnly else products.query(query_texts=query, n_results=100)
        directMatches = products.get(where_document={"$contains": query.lower()})
    except cdberr.NotFoundError:
        print("Database changed, restart required.")
        return []
    if embeddingMatches["metadatas"] != None and embeddingMatches["distances"] != None and directMatches["metadatas"] != None:
        #query database for matches
        embeddingInfos = [ProductData.model_validate(decomposeTags(meta)) for meta in embeddingMatches["metadatas"][0]]
        directInfos = [ProductData.model_validate(decomposeTags(meta)) for meta in directMatches["metadatas"]]
        directInfos = [pd for pd in directInfos if pd.matches(query)]

        #remove direct matches
        embeddingInfos = list(set(embeddingInfos) - set(directInfos))

        # Pair productInfos with distances so sorting is easier.
        infosDict = {i: (embeddingInfos[i], embeddingMatches["distances"][0][i]) for i in range(len(embeddingInfos))}
        queryEmbedding = embed(query)
        directsDict = {i: (directInfos[i], embeddingDistance(queryEmbedding, directInfos[i].text())) for i in range(len(directInfos))}

        #sort by distance
        infosList = list(infosDict.values())
        infosList.sort(key=lambda t: t[1])
        infosList.sort(key=lambda t: int(t[0].available), reverse=True)
        directsList = list(directsDict.values())
        directsList.sort(key=lambda t: t[1])
        directsList.sort(key=lambda t: int(t[0].available), reverse=True)

        #join back and return
        finalList = [t[0] for t in directsList + infosList][:10]
        finalList.sort(key=lambda pd: int(pd.available), reverse=True)
        return finalList
    else:
        print("Malformed product data from query.")
        return []
    
# search full database for textual matches
# allow user to choose between specifics (textual match and above certain confidence threshold) or plus recommended
# better data encapsulation (put field names and delimeters into the string to be emebdded)

# Bulk import: 
# Fields: name, desc, tags, price
# upload image

# slides
# problem stamenet, user req., strageties, solutions, future improvements
# Deadline: 11 am Thu prod., 5 pm Wed pres.