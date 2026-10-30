"""Entry point used by the standalone Windows package."""
import multiprocessing
from tracegarden.__main__ import main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
