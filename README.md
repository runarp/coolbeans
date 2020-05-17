# coolbeans -- Tools for beancount

A collection of utilities and importers I use for my beancount workflow.

I'll try to keep this project "generic" and "configurable" so, perhaps, someone else could use it.

# ideas

## Dynamic import.py
Make CONFIG an iterable that introspects existing file (or loaded file?).

Each account could have it's own import meta-data.  The Pros are:

* We don't "loose" accounts
* Less work keeping Multiple account files in sync with importers
* problem: If the importer changes over time?
    * this might not be an issue after the initial loading.

## Roundtrip Some of the files

Create a "Sorter" based on:

    YYYY, Account, MM, DD, meta['sort']

* each year could be it's own bean file (or folder?)
* At the start of the year a simple pad/balance can give a sane starting point
* intra-Year accounts can be opened/closed, but generally are manged in the root file.

# Duplicate Entry problem

* For "already loaded" entries, we match on the meta['unique-id'], these are easy if available
* For "payment" records (Asset->Liability) or (Asset->Asset), if we know at the
  time of reading (like CC), the transaction is kept but Mangled with a 0.00
  Balance.  such that it shows up, but the actual amount is in the meta of the
  payment:

    2020-04-24 ! "Payment Received"
      ofx-fitid: "75140210115007025646907108"
      ofx-type: "CREDIT"
      delete-flag: "DUPLICATE-LEG"
      * Liabilities:CreditCard:Barklays:Aviator   0 USD
      T Assets:Banking:BofA:Checking              0 USD
        amount: 63.49

* flags.FLAG_TRANSFER = 'T' ; https://github.com/xuhcc/beancount/blob/master/beancount/core/flags.py

# Beans as a Journal

If I sort each file purely by time (not by account). Things start to look more like
a "journal of your life" than a bunch of statements.  Each Day/Week/Month becomes a
section in a generated/managed files.  Ideally, we can still keep the round-trip
capabilities of the system.  But we have a fixed sorter.

Section headers can be auto-generated:

* January
** Week 2
** Week 3
* February

Because we are forcing accounts, we have to white-list the Accounts that go
into the annual file?  (I want to exclude trading accounts)
