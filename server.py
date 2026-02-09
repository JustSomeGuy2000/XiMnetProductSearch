import fastapi as fast
import src.process as src

app = fast.FastAPI()

@app.get("/search/")
async def search(query: str, exactOnly: bool) -> list[src.ProductData]:
    return src.search(query, exactOnly)

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, port=8000)