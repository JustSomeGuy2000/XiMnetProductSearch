# Documentation

## Server
- Found in ./server.py
- A simple server implemented in Python using `fastapi`.
- Exposes a single GET endpoint, `/search/`, that takes two parameters in the query string: `query` and `exactOnly`.
- Calls to this endpoint return the results of the product search.
- If `exactOnly` is `True`, only exact textual matches will be returned, with a maximum of 10. If it is `False`, exactly 10 results will be returned, ordered by embedding similarity.

## Client (CLI)
- Found in ./cliClient.py
- A CLI for executing product searches
- Allows the user to specify the state of the `exactOnly` flag and persist it across sessions.
- Sends a GET request to the server with the user's search query and the `exactOnly` flag, and displays the results (as far as it can) upon receiving the response.

## Search function
- Found in ./src/process.py
- Queries the database twice, once for similar embeddings to the query, and once with a direct textual search using `chromadb`'s built-in filter system.
- Product data is serialised into a  dictionary for storage in the database, as `chromadb` is primarily an embedding database.
    - It is converted back into a proper object for use.
- If `exactOnly` is `True`, the embedding search is skipped and its result is replaced by an empty object.
    - As `exactOnly` was a requirement added later, the function is contingent around the embedding matches object existing, so it was easier to cheese it rather than rewriting everything.
- Removes exact matches from the embedding matches by temporarily turning them both into sets and taking the difference.
- The two lists of matches are paired with their embedding similarities (relative to the search query) for sorting.
    - For the embedding matches, their similarites are included in the results object returned by `chromadb`, so they are just extracted from there.
    - Similarities are not included for direct searches, so those are manually embedded to find the similarity.
- Both lists are sorted.
    - First, by decreasing order of similarity
    - Then, products that are not available are moved to the bottom.
- The lists are concatenated.
    - Doing this last ensures that exact matches are always above embedding matches.
- The final list is returned.

# Limitations
- Lack of serious UI.
    - CLIs quickly become troublesome to navigate and manage as more and more menus and options are added.
- The textual search does not consider context or relevance, only presence of the search term.
- Embeddings are generated from text, meaning that the product data object must be converted to a string, losing most of the meaning associated with its fields.
