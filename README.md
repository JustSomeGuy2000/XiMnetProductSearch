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
- Bulk loading of product data from PDFs or images remains poorly implemented.

# PDF and Image Processing
## First attempt: `unstructured`
- The `unstructured` module can use a combination of the `poppler` library, Tesseract OCR engine, and `detectron2_onnx` layout detection model to partition PDFs and images into chunks and extract structured infromation from text and layout.
- It can attempt to extract tables, but only if lines are clearly defined.
    - Implicit tables amde by arrangements of text are not detected.
- However, the open source library (as opposed to their paid service) has few options for customisation and is not very good.
    - OCR is unusably inaccurate.
    - Many duplicates appear in the output.
    - Relations between content are poorly inferred.
    - Some symbol images are erroneously converted into text.
## Second attempt: `pymupdf`
- The `pymupdf` module is a PDF manipulation library that can extract text from PDFs by directly reading file data, or using Tesseract OCR for flat PDFs and images.
- It has three output options: JSON, markdown, and plain text.
- Although it reads PDFs in internal order, which may not correspond to reading order, there is an option to automatically sort by inferrred order. 
- Unfortunately, there are still issues:
    - Plain text carries too little information regarding the properties of text, which is crucial in determining relation.
    - Markdown mode outputs a string with markdown elements, which requires heavy processing to extract information. While containing more information than plain text, it still carries too little.
    - JSON mode is extremely verbose. There was not enough time to thoroughly analyse it and derive a general way of ordering the elements using the information contained within.
- In any case, a purely deterministic method of ordering would likely fail for the majority of cases due to the huge possible variance of inputs.
## Third attmept: `donut-python`
- The `donut-python` module uses a specialised AI model called DonUT to extract various types of information from documents. Uses include:
    - Identifying document type
    - Answering questions about the document
    - **Producing structured JSON detailing the document's contents.**
- It attempts to import a nonexistent attribute of `transformers.modeling_utils` called `PretrainedConfig`
    - The class now resides in `transformers`
- After manually correcting the import, the module also attempts to import a nonexistent attribute of `pyarrow` called `PyExtensionType`
    - THis is due to `PyExtensionType` being renamed to `ExtensionType` some time in the past.
- After installing the correct `pyarrow` version, the model reports a severe mismatched between expected and obtained model weights.
- It also attempts to access a nonexistent attribute of itself called `all_tied_weights_keys`.
- At this point, I abandoned the pursuit.
- Unfortunately, it was also the most accurate option (if trials done by other people on the Internet were anything to go by).
- This misadventure took the entire morning (until 11:58 AM to be exact).