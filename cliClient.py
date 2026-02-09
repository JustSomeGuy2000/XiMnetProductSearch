import os
import copy
import inspect as insp
import requests as req
import pydantic as pyd
import src.database as src
from abc import ABC, abstractmethod
from typing import Callable, NamedTuple

class NoContext(NamedTuple): ...
noContext = NoContext()
class Menu[C: NamedTuple](ABC):
    @staticmethod
    def loop(conditions: list[Callable[[str], bool]], failureMessage: str = "Invalid input. Please try again >>> ") -> str:
        while True:
            opt = input()
            if all([f(opt) for f in conditions]):
                return opt
            print(failureMessage)

    @staticmethod
    def isInt(opt: str) -> bool:
        try:
            int(opt.strip())
            return True
        except ValueError:
            return False
        
    @staticmethod
    def strInRange(start: int, end: int) -> Callable[[str], bool]:
        def condition(opt: str):
            num = int(opt)
            if num >= start and num <= end:
                return True
            return False
        return condition
    
    @staticmethod
    def enterToContinue(message: str = "Enter to continue...") -> str:
        return input(message)

    def __init__(self) -> None:
        raise RuntimeError("Menus cannot be instantiated.")

    @classmethod
    @abstractmethod
    def display(cls, env: "CLI", context: C) -> str: ...

    @classmethod
    @abstractmethod
    def choose(cls, env: "CLI", context: C, choice: str) -> None: ...

class MainMenu(Menu[NoContext]):
    @classmethod
    def display(cls, env: "CLI", context: NoContext) -> str:
        print("\n")
        print("Product Search Client: CLI\n1. Search\n2. Settings\n3. Quit\nInput option number >>> ", end="")
        return Menu.loop([Menu.isInt, Menu.strInRange(1, 3)])
    
    @classmethod
    def choose(cls, env: "CLI", context: NoContext, choice: str):
        if choice == "1":
           env.switchMenu(SearchMenu, noContext)
        elif choice == "2":
            env.switchMenu(SettingsMenu, noContext)
        elif choice == "3":
            print("Quitting...")
            env.running = False

class SearchMenu(Menu[NoContext]):
    @classmethod
    def display(cls, env: "CLI", context) -> str:
        return input("Enter search query: ")
    
    @classmethod
    def choose(cls, env:" CLI", context, choice: str):
        try:
            resultJsons: list[dict[str, object]] = req.get(f"http://127.0.0.1:8000/search/", {"query": choice, "exactOnly": env.settings.exactOnly}).json()
            result = [src.ProductData.model_validate(d) for d in resultJsons]
            env.substituteMenu(ResultsDisplayMenu, ResultsDisplayMenuContext(result))
            return
        except req.ConnectionError as e:
            import urllib3.exceptions as excs
            if isinstance(e.args[0], excs.MaxRetryError):
                print("Connection could not be made.")
            else:
                print(f"Connection error: {e}")
        env.back()

class ResultsDisplayMenuContext(NamedTuple):
    results: list[src.ProductData]
class ResultsDisplayMenu(Menu[ResultsDisplayMenuContext]):
    @classmethod
    def display(cls, env: "CLI", context) -> str:
        length = 0
        for ind, pd in enumerate(context.results):
            print(f"{ind + 1}. {pd.name}")
            length = ind
        print(f"{length + 2}. Back")
        print("Enter option >>> ", end="")
        return Menu.loop([Menu.isInt, Menu.strInRange(1, length + 2)])
    
    @classmethod
    def choose(cls, env: "CLI", context, choice: str):
       for ind, pd in enumerate(context.results):
           if str(ind + 1) == choice:
               env.switchMenu(PDDisplayMenu, PDDisplayMenuContext(pd))
               return
       env.back()

class PDDisplayMenuContext(NamedTuple):
    result: src.ProductData
class PDDisplayMenu(Menu[PDDisplayMenuContext]):
    @classmethod
    def display(cls, env: "CLI", context: PDDisplayMenuContext) -> str:
        pd = context.result
        print(insp.cleandoc(f"""Product: {pd.name} ({pd.sku})
                            {"AVAILABLE" if pd.available else "NOT AVAILABLE"}
                            {pd.desc}

                            Price: {pd.price:.2f}
                            Tags: {", ".join(pd.tags)}"""))
        return Menu.enterToContinue()
    
    @classmethod
    def choose(cls, env: "CLI", context: PDDisplayMenuContext, choice: str):
        env.back()

class SettingsMenu(Menu[NoContext]):
    @classmethod
    def display(cls, env: "CLI", context: NoContext) -> str:
        print(insp.cleandoc(f"""Settings:
              1. Show recommended products ({not env.settings.exactOnly})
              2. Back
              Enter option >>> """), end="")
        return Menu.loop([Menu.isInt, Menu.strInRange(1, 2)])
    
    @classmethod
    def choose(cls, env: "CLI", context: NoContext, choice: str) -> None:
        if choice == "1":
            env.switchMenu(SettingsExactOnlyMenu, noContext)
        elif choice == "2":
            env.back()
        return
    
class SettingsExactOnlyMenu(Menu[NoContext]):
    @classmethod
    def display(cls, env: "CLI", context: NoContext) -> str:
        print(insp.cleandoc("""Show only close matches, or recommended products as well:
                            1. Only close
                            2. Recommended
                            Enter option >>> """), end="")
        return Menu.loop([Menu.isInt, Menu.strInRange(1, 2)])
    
    @classmethod
    def choose(cls, env: "CLI", context: NoContext, choice: str) -> None:
        if choice == "1":
            env.settings.exactOnly = True
        elif choice == "2":
            env.settings.exactOnly = False
        env.settingsChanged = True
        env.back()

class Settings(pyd.BaseModel):
    exactOnly: bool = False

SETTINGS_FILE = "/settings.json"
dir = os.path.dirname(os.path.abspath(__file__))
class CLI:
    def __init__(self):
        self.backstack: list[tuple[type[Menu], NamedTuple]] = []
        self.menu: type[Menu] = MainMenu
        self.context: NamedTuple = noContext
        self.running: bool = False
        self.settingsPath = dir + SETTINGS_FILE
        self.settingsChanged: bool = False
        if os.path.isfile(self.settingsPath):
            with open(self.settingsPath, "r") as file:
                try:
                    self.settings = Settings.model_validate_json(file.read())
                except pyd.ValidationError:
                    print("Malformed settings data, resetting...")
                    self.settings = Settings()
                    self.settingsChanged = True
        else:
            self.settings = Settings()
            self.settingsChanged = True

    def start(self):
        self.running = True
        while self.running:
            currentMenu = copy.copy(self.menu)
            opt = currentMenu.display(self, self.context)
            currentMenu.choose(self, self.context, opt)
        if self.settingsChanged:
            with open(self.settingsPath, "w") as file:
                file.write(self.settings.model_dump_json())

    def switchMenu[C: NamedTuple](self, to: type[Menu[C]], context: C):
        self.backstack.append((self.menu, copy.copy(self.context)))
        self.menu = to
        self.context = context

    def substituteMenu[C: NamedTuple](self, to: type[Menu[C]], context: C):
        self.menu = to
        self.context = context

    def back(self):
        last = self.backstack.pop()
        self.menu = last[0]
        self.context = last[1]

if __name__ == "__main__":
    CLI().start()