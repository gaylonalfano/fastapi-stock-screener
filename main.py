# fastapi-stock-screener/main.py
import models
import yfinance
from fastapi import FastAPI, Request, Depends, BackgroundTasks
from fastapi.templating import Jinja2Templates
from database import SessionLocal, engine
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models import Stock

app = FastAPI()

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Tell Jinja2Templates where our templates are located:
templates = Jinja2Templates(directory="templates")


# Our POST request only requires a symbol. Let's extend Pydantic's BaseModel
# to find the structure of the request.
class StockRequest(BaseModel):
    symbol: str


# Retreive our database session dependency:
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


# Base route for out dashboard. Eventually return template
@app.get("/")
def dashboard(
    request: Request,
    forward_pe=None,
    dividend_yield=None,
    ma50=None,
    ma200=None,
    db: Session = Depends(get_db),
):
    """
    Displays the stock screener dashboard/homepage.
    """
    # Create db.query() object for stocks. Add .all() converts to list!
    stocks = db.query(Stock)
    # print(type(stocks))  # <class 'sqlalchemy.orm.query.Query'>

    # Apply filters to our stocks if passed
    if forward_pe:
        stocks = stocks.filter(Stock.forward_pe < forward_pe)

    if dividend_yield:
        stocks = stocks.filter(Stock.dividend_yield > dividend_yield)

    if ma50:
        stocks = stocks.filter(Stock.price > Stock.ma50)

    if ma200:
        stocks = stocks.filter(Stock.price > Stock.ma200)

    stocks = stocks.all()

    return templates.TemplateResponse(
        name="dashboard.html",
        context={
            "request": request,
            "stocks": stocks,
            "dividend_yield": dividend_yield,
            "forward_pe": forward_pe,
            "ma200": ma200,
            "ma50": ma50,
        },
    )


# Helper function to use with BackgroundTasks to fetch YF data
# The 'id' is a reference to primary key in database
def fetch_stock_data(id: int):
    # Create a new db session in the background
    db = SessionLocal()
    # Query the db for the matching stock record using this id
    stock = db.query(Stock).filter(Stock.id == id).first()

    # Test that our function even works before fetching from YF
    # by manually updating 'forward_pe' field
    # stock.forward_pe = 10

    # Get data from YF and map to our table columns
    yahoo_data = yfinance.Ticker(stock.symbol)

    stock.ma200 = yahoo_data.info["twoHundredDayAverage"]
    stock.ma50 = yahoo_data.info["fiftyDayAverage"]
    stock.price = yahoo_data.info["previousClose"]
    stock.forward_pe = yahoo_data.info["forwardPE"]
    stock.forward_eps = yahoo_data.info["forwardEps"]
    # Some stocks don't give dividend_yield, so add conditional
    if yahoo_data.info["dividendYield"] is not None:
        stock.dividend_yield = yahoo_data.info["dividendYield"] * 100

    # Update the record
    db.add(stock)
    db.commit()


# Add a post endpoint to add new stock to database
# Make it async if using BackgroundTasks
@app.post("/stock")
async def create_stock(
    stock_request: StockRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Creates a stock and stores in database.
    """
    # Instantiate our Stock model
    stock = Stock()
    # Our database model has 'symbol'.  And our request has 'symbol'
    stock.symbol = stock_request.symbol

    # Add this object to our database session and commit to database
    db.add(stock)
    db.commit()

    # Kick off a single background task after inserting to database
    background_tasks.add_task(fetch_stock_data, stock.id)

    return {"code": "success", "message": "stock was added to the database"}
