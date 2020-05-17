"""
Utilities for Managing VIM Buffers and beancount
"""
import datetime
import beancount
import coolbeans

def create_entry(vim):
    """
    Create a new Beancount Transaction Entry at the current cursor position.

    PoC stage
    """

    cb = vim.current.buffer
    cw = vim.current.window
    (row, col) = cw.cursor
    r = cb.range(row, row)

    today = datetime.datetime.today()
    insert_text = f"{today.strftime('%Y-%m-%d')} * "" """

    r.append(insert_text)

    cw.cursor = (row+1, len(insert_text)-1)

    return

    current_line = cb[row-1]
    if current_line.strip():
        return
    cb.append = []
    cw.cursor = (row, 15)
