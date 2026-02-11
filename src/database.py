import json
import numpy as np
import tkinter as tk
import ollama as ollm
import chromadb as cdb
import pydantic as pyd
from typing import Any, Literal
from tkinter import filedialog as fd
import unstructured.documents.elements as unstels

root = tk.Tk()
root.withdraw()
root.call('wm', 'attributes', '.', '-topmost', True)

class OllamaEmbedder(cdb.EmbeddingFunction):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def __call__(self, docs: cdb.Documents) -> cdb.Embeddings:
        vectors = ollm.embed("embeddinggemma", docs).embeddings
        return [np.array(v, dtype=np.float32) for v in vectors]
    
class ProductData(pyd.BaseModel):
    name: str
    desc: str
    sku: str
    price: float
    tags: list[str]
    available: bool = True

    def matches(self, to: str) -> bool:
        l = to.lower()
        return l in self.name.lower() or l in self.desc.lower() or l in self.tags
    
    def text(self) -> str:
        return f"NAME: {self.name.lower()}; DESCRIPTION: {self.desc.lower()}; TAGS: {";".join(self.tags).lower()}"

    def toDB(self):
        dump = self.model_dump()
        dump["tags"] = ";".join(self.tags)
        return DBProductData(id=self.sku, text=self.text(), metadata=dump)
    
    def __hash__(self) -> int:
        return hash(self.model_dump_json())
    
class DataPart:
    def __init__(self, name: str | None = None, desc: str | None = None, sku: str = "", price: float | None = None, tags: list[str] = [], available: bool = True) -> None:
        self.name = name
        self.desc = desc
        self.sku = sku
        self.price = price
        self.tags = tags
        self.available = available

    def toData(self) -> ProductData:
        if self.name == None or self.desc == None or self.price == None:
            raise TypeError("Missing fields.")
        return ProductData(name=self.name, desc=self.desc, sku=self.sku, price=self.price, tags=self.tags, available=self.available)
    
def pdfParseUnst() -> None:
    import unstructured.partition.pdf as unstpdf
    file = fd.askopenfile("rb", filetypes=[("PDF", "*.pdf")])
    pdf = unstpdf.partition_pdf(file=file, strategy="auto", languages=["eng"], extract_image_block_types=["Image", "Table"])
    productDataUnst = extractProductDataUnst(pdf)
    print(productDataUnst)

def imgParseUnst() -> None:
    import unstructured.partition.image as unstimg
    file = fd.askopenfile("rb", filetypes=[("Image (PNG)", "*.png"), ("Image (HEIC)", "*.heic"), ("Image (JPG)", "*.jpg"), ("Image (JPEG)", "*.jpeg")])
    img = unstimg.partition_image(file=file, strategy="hi_res", languages=["eng"], extract_image_block_types=["Image", "Table"])
    productDataUnst = extractProductDataUnst(img)
    print(productDataUnst)

def extractProductDataUnst(elements: list[unstels.Element]) -> list[ProductData]:
    prices: list[float] = []
    last: unstels.Element = elements[0]
    parts: list[DataPart] = []
    part = DataPart()
    titleEncountered: bool = False
    for el in elements:
        eltype = type(el)
        if el.text == last.text and type(last) == unstels.Title and eltype == unstels.Text:
            continue
        match eltype:
            case unstels.Title:
                part.name = el.text
                titleEncountered = True
            case unstels.Text | unstels.ListItem | unstels.NarrativeText:
                if not titleEncountered:
                    continue
                try:
                    prices.append(int(el.text))
                except ValueError:
                    if part.desc == None:
                        part.desc = ""
                    part.desc += " " + el.text
            case _:
                print(f"Unknown element type: {eltype}, containing \"{el.text}\"")
        last = el
        if part.name != None and part.desc != None:
            parts.append(part)
            part = DataPart()
    priceNum = len(prices)
    for ind, part in enumerate(parts):
        part.price = prices[ind] if ind < priceNum else 0
    return [dp.toData() for dp in parts]

def pdfParseMu() -> None:
    import pymupdf as pymu
    import pymupdf.layout as _
    import pymupdf4llm as pymul
    file = fd.askopenfilename(filetypes=[("PDF", "*.pdf")])
    pdf = pymu.open(file)
    productDataMu = pymul.to_json(pdf, header=False, footer=False)
    for page in pdf:
        print(page.get_text("text", sort=True))
    #print(scheme(json.loads(productDataMu)))
    #print([pdfmu.get_page_text(i) for i in range(pdfmu.page_count)])

type schemePrimitives = Literal["str"] | Literal["int"] | Literal["bool"] | Literal["?"] | Literal["float"]
type schemeParts = schemePrimitives | list[schemeParts] | dict[str, schemeParts]
def toPrimtiveOrUnknown(type: str) -> schemePrimitives:
    if type == "str" or type == "int" or type == "bool" or type == "float":
        return type
    else:
        return "?"
def scheme(of: dict[str, Any]) -> dict[str, schemeParts]:
    res: dict[str, schemeParts] = {}
    for key, val in of.items():
        valType = type(val)
        if valType is dict:
            res[key] = scheme(val)
        elif valType is list:
            res[key] = listScheme(val) if len(val) > 0 else ["?"]
        elif valType is str or valType is bool or valType is int or valType is float:
            res[key] = toPrimtiveOrUnknown(valType.__name__)
        else:
            res[key] = "?"
    return res

def listScheme(of: list[Any]) -> list[schemeParts]:
    res: list[schemeParts] = []
    if len(of) < 1:
        res.append("?")
    else:
        val = of[0]
        valType = type(val)
        if valType is dict:
            res.append(scheme(val))
        elif valType is list:
            res.append(scheme(val[0]) if len(val) > 0 else ["?"])
        elif valType is str or valType is bool or valType is int or valType is float:
            res.append(toPrimtiveOrUnknown(valType.__name__))
        else:
            res.append("?")
    res.append(len(of)) # type: ignore
    return res

class DBProductData(pyd.BaseModel):
    id: str
    text: str
    metadata: dict[str, str | bool | float]

if __name__ == "__main__":
    import os
    import json
    import process as src

    dir = os.path.dirname(os.path.abspath(__file__))
    chroma = cdb.PersistentClient()
    products = chroma.get_or_create_collection("products", embedding_function=OllamaEmbedder())

    while True:
        print("\n")
        opt: int = 0
        while True:
            option = input(
"""Database management
1. Add entries from JSON file
2. Load test entries to file
3. Clear database
4. Peek database
5. Search database
6. Upsert entries from file
7. Add entries from PDF file
8. Add entries from image file
9. Quit
Input option number >>> """)
            try:
                opt = int(option.strip())
                print("\n")
                break
            except (TypeError, ValueError):
                print("Please input a valid option.")
        
        if opt == 1:
            fileName = input("Enter file name >>> ")
            print("Loading...")
            entriesList: list[DBProductData] = []
            with open(dir + fileName) as file:
                data: dict = json.load(file)
            for d in data:
                try:
                    entriesList.append(ProductData.model_validate(d).toDB())
                except pyd.ValidationError as e:
                    print(f"Validation error: {e}")
            products.add([pd.id for pd in entriesList], metadatas=[pd.metadata for pd in entriesList], documents=[pd.text for pd in entriesList])
            print("Finished!")

        elif opt == 2:
            fileName = input("Enter file name >>> ")
            dataset = int(input("Enter dataset number >>> "))
            print("Loading...")
            with open(dir + fileName, "w") as file:
                entries: list[list[ProductData]] = [[
                    ProductData(name="Americano", desc="Pure black coffee, no milk or sugar or anything. Very strong in its bitterness.", sku="CNB0001", price=9.99, tags=["black", "coffee", "sugarless", "dairyless"], available=False),
                    ProductData(name="Latte", desc="A shot of coffee mixed with a shot of milk (other milks available) in a roughly equal ratio. Preserves the bitterness and other tones of the coffee while balancing it out with sweetness and creaminess.", sku="CNM0010", price=10.89, tags=["white", "coffee", "dairy", "other milk available"]),
                    ProductData(name="Affogato", desc="A cup of espresso with some milk in it. The rest of the diary content comes from a scoop of vanilla ice cream on top. It adds a pleasant sweetness to the coffee as well as a novel vanilla flavour.", sku="CIM0055", price=16.50, tags=["white", "coffee", "dairy", "ice cream vanilla"]),
                    ProductData(name="Mocha", desc="A mix of roughly equal parts milk, coffee and choclate, combining the caffeine boost and pleasant bitterness of coffee with the sweet earthiness of chocolate.", sku="CNMh011", price=15.00, tags=["white", "coffee", "chocolate", "dairy"]),
                    ProductData(name="Matcha Latte", desc="A drink made from crushed and treated green tea leaves imported straight from Japan mixed with a dash of milk. It has a strong umami flavour, and an equally strong bright green colour. Very popular in contemporary times.", sku="TgNM0125", price=9.99, tags=["green", "tea", "matcha", "leaves", "umami", "dairy"]), #5
                    ProductData(name="Hot Chocolate", desc="Chocolate powder dissolved in water, with a good amount of milk mixed in. An age-old classic for cold times.", sku="HNM0001", price=6.99, tags=["no coffee", "dairy", "other milks available", "hot", "chocolate"]),
                    ProductData(name="Water", desc="Plain water. Comes hot, cold or lukwarm.", sku="WNN0001", price=2.00, tags=["no coffee", "no dairy", "plain", "any temperature", "water"]),
                    ProductData(name="Green Tea", desc="Although this and matcha are made of the same kind of leaves, this is made by steeping the leaves while they are still contained in a bag. Has a weaker and more subtle flavour than matcha, best enjoyed without milk.", sku="TgNN0001", price=8.25, tags=["green", "tea", "leaves", "hot", "weak", "subtle"]),
                    ProductData(name="Earl Grey Tea", desc="One of the most ancient and revered drinks in the world, with a smooth flavour, usually with a sugar cube or two mixed in.", sku="TNS0001", price=5.45, tags=["earl grey", "tea", "dairyless", "leaves", "hot"]),
                    ProductData(name="Melted Cheese", desc="A pot of freshly melted cheese of various kinds (enquire within for the exact mix), bubbling and boiling. The combination of the myriad of flavours creates a truly unique culinary exprience.", sku="ONN0101", price=15.90, tags=["no coffee", "no tea", "cheese", "oddities", "no nothing except cheese", "no milk", "no sugar"]), #10
                    ProductData(name="Mayonnaise", desc="Pure mayonnaise in a large glass. Not suitable for thise with egg allergies. Although slightly gelatinous, mayonnaise is so smooth and creamy that the mere sensation of it sliding down your throat when you swallow is delightful.", sku="ONN0001", price=13.99, tags=["no coffee", "no tea", "mayonnaise", "oddities", "no nothing except mayo", "no milk", "no sugar"]),
                    ProductData(name="Croque Monsieur", desc="The French version of a ham-and-cheese sandiwich, so of course it had to be overcomplicated. Thick slices of chicken ham layered between multiple cheeses (enquire within for details) and leaves of lettuce, topped with a bechamel sauce.", sku="SHC0090", price=12.90, tags=["pastry", "bread", "ham", "cheese", "breakfast", "milk", "sauce"], available=False),
                    ProductData(name="Croque Madame", desc="An even better version of the already eminent Croque Monsieur. The addition of a drippy poached egg on top of the bread completes the picture.", sku="SHC0091", price=13.99, tags=["pastry", "bread", "ham", "cheese", "breakfast", "milk", "sauce", "egg"]),
                    ProductData(name="Croissant", desc="The most recognisable French pastry. Dozens of flaky layers of pastry encased within a crispy shell of the immediately recognisable shape.", sku="BNC0005", price=4.00, tags=["pastry", "bread", "plain", "breakfast"]),
                    ProductData(name="French Toast", desc="A pastry so excellent, so delicious, they named a whole country after it. Thick slices of white bread dipped in beaten egg and fried until yellow-brown. Comes with butter and syrup on the side to spread. Enquire within for a cheese spread.", sku="BNE5000", price=15.85, tags=["pastry", "bread", "cheese", "breakfast", "syrup", "butter", "egg"]), #15
                    ProductData(name="Big Lunch", desc="The noontime counterpart of the Big Breakfast. Comes with all the usual trappings, plus a chicken drumstick and bowl of rice.", sku="AAA6327", price=26.30, tags=["lunch", "rice", "meat", "chicken", "egg", "sausage", "mushroom", "cherry tomato"]),
                    ProductData(name="Shrimp Fried Rice", desc="Prepared by our finest shrimp chefs. A large plate of rice expertly fried with egg, assorted vegetables, and shrimp.", sku="RAE0400", price=16.00, tags=["rice", "egg", "vegetables", "plain", "shrimp", "lunch"]),
                    ProductData(name="Spagetthi Bolognaise", desc="Italian noodles in the classic Bolognaise style, that is, a rich tomato sauce. Slices of chicken are added for protein.", sku="NCT0342", price=19.10, tags=["noodles", "pasta", "tomato", "sauce", "lunch", "chicken"]),
                    ProductData(name="Carbonara Pasta", desc="Another widely-loved way of cooking pasta. Served denched in an off-white gooey sauce made from milk and sugar, with strips of salty duck placed on top.", sku="NDC8234", price=21.05, tags=["noodles", "pasta", "milk", "sugar", "sauce", "lunch", "duck"]),
                    ProductData(name="Smoked Salmon", desc="A single, massive fillet of smoked salmon, seasoned to perfection. Half a lemon is provided to squeeze on top.", sku="FNN0237", price=32.95, tags=["fish", "smoked", "salmon", "dinner", "lemon", "seasoned"]), #20
                ], [
                    ProductData(name="iPhone 17 Pro", desc="iPhone 17, newest version, with increased capabilities from Pro specification", sku="APP1700", price=13.99, tags=["apple", "phone"]),
                    ProductData(name="iPhone 16", desc="Second-last generation of iPhone, standard model.", sku="APN1600", price=13.99, tags=["apple", "phone"]),
                    ProductData(name="iPhone 13", desc="Older version of iPhone, standard model.", sku="APN1300", price=13.99, tags=["apple", "phone"]),
                    ProductData(name="iPhone X Pro Max", desc="Highest specs (Pro Max) version of 10th iPhone, named X after the Roman numeral.", sku="APPm1000", price=13.99, tags=["apple", "phone"]),
                    ProductData(name="iPad Air 2", desc="Second-generation small Apple tablet", sku="ATA0200", price=13.99, tags=["apple", "tablet"]), #5
                    ProductData(name="iPad Air", desc="First-generation small Apple tablet", sku="ATA0000", price=13.99, tags=["apple", "tablet"]),
                    ProductData(name="Samsung Galaxy A25", desc="Newest mobile phone from Samsung Galaxy mid-series (A)", sku="SPA0250", price=13.99, tags=["samsung", "phone"]),
                    ProductData(name="Samsung Galaxy A24", desc="Newest mobile phone from Samsung Galaxy mid-series (A)", sku="SPA0240", price=13.99, tags=["samsung", "phone"]),
                    ProductData(name="Samsung Galaxy A20", desc="Older mobile phone from Samsung Galaxy mid-series (A)", sku="SPA0200", price=13.99, tags=["samsung", "phone"]),
                    ProductData(name="Samsung Galaxy A15", desc="Old mobile phone from Samsung Galaxy mid-series (A)", sku="SPA0150", price=13.99, tags=["samsung", "phone"]), #10
                    ProductData(name="Samsung Galaxy S30", desc="Newest mobile phone from Samsung Galaxy high-end series (S)", sku="SPS3000", price=13.99, tags=["samsung", "phone"]),
                    ProductData(name="Samsung Galaxy S20", desc="Older mobile phone from Samsung Galaxy high-end series (S)", sku="SPS2000", price=13.99, tags=["samsung", "phone"]),
                    ProductData(name="Nothing Phone (3a)", desc="Newest mobile phone by breakout brand Nothing, known for their complex sci-fi-inspired designs.", sku="OPN0031", price=13.99, tags=["nothing", "phone"]),
                    ProductData(name="Nokia 1200", desc="Nokia phone from old storage, will break the ground if you drop it.", sku="NHN1200", price=13.99, tags=["nokia", "phone"]),
                    ProductData(name="Nokia 1110", desc="Nokia phone from old storage, will break the ground if you drop it.", sku="NHN1100", price=13.99, tags=["nokia", "phone"]), #15
                    ProductData(name="Samsung Galaxy Tab S10", desc="S10 tablet from Samsung", sku="SGT1910", price=13.99, tags=["samsung", "tablet"]),
                    ProductData(name="Samsung Galaxy Tab S7", desc="S7 tabler from Samsung", sku="SGT1907", price=13.99, tags=["samsung", "tablet"]),
                    ProductData(name="1 Plus Nord", desc="Popular phone from little-known brand 1+ (has many alternate spellings too)", sku="PPN0101", price=13.99, tags=["1 plus", "one plus", "1plus", "oneplus", "phone"]),
                    ProductData(name="Huawei P40", desc="Huawei P40 mobile phone", sku="HPN1640", price=13.99, tags=["huawei", "phone"]),
                    ProductData(name="Huawei Mate50", desc="Huawei P40 mobile phone", sku="HPM0050", price=13.99, tags=["huawei", "phone"]), #20
                ]]
                json.dump([e.model_dump() for e in entries[dataset]], file)
            print("Finished!")

        elif opt == 3:
            print("Clearing")
            chroma.delete_collection("products")
            chroma.create_collection("products", embedding_function=OllamaEmbedder())
            products = chroma.get_collection("products", embedding_function=OllamaEmbedder())
            print("Finished!")

        elif opt == 4:
            print(products.peek()["metadatas"])

        elif opt == 5:
            query = input("Enter search query >>> ")
            print("Searching...")
            print(src.search(query, False))

        elif opt == 6:
            fileName = input("Enter file name >>> ")
            print("Loading...")
            entriesList: list[DBProductData] = []
            with open(dir + fileName) as file:
                data: dict = json.load(file)
            for d in data:
                try:
                    entriesList.append(ProductData.model_validate(d).toDB())
                except pyd.ValidationError as e:
                    print(f"Validation error: {e}")
            products.upsert([pd.id for pd in entriesList], metadatas=[pd.metadata for pd in entriesList], documents=[pd.text for pd in entriesList])
            print("Finished!")

        elif opt == 7:
            GETFILE_TYPE: Literal["unst"] | Literal["mu"] = "unst"
            if GETFILE_TYPE == "unst":
                pdfParseUnst()
                pass
            elif GETFILE_TYPE == "mu":
                pdfParseMu()
                pass

        elif opt == 8:
            imgParseUnst()
            pass

        elif opt == 9:
            print("Quitting...")
            break