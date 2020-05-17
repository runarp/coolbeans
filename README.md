# coolbeans -- Tools for beancount

A collection of utilities and importers I use for my beancount workflow.

I'll try to keep this project "generic" and "configurable" so, perhaps, someone
else could use it.


## Commans (current)

There are two command-line utilties so far.  cool-organizer and cool-match

###  cool-organizer
cool-organizer will modify a file in-place, filing new entries:

  cool-organizer -e root.bean -m 2020.bean new_entries.bean -y 2020

Read the root.bean and file entries from new_entires.bean into the
2020.bean.  the -y filter enforces the filing to ignore any other years from
the new_entries.

### cool-match
Allows for applying a set of regex rules to an existing file.  This is very much
wip.  Current usage is:

    cool-match -e 2020.bean -r rules.yaml > stagefile.bean

Then you can organize the entries:

    cool-organizer -e root.bean -m 2020.bean stagefile.bean -y 2020

## ib importer

This is a regular importer that implements most of the class (name files etc.).

The input files are XML generated from the Interactive Broker's IBFlex report.

Each transaction has an extra 'match-key' meta attribute, used for
de-duplication.

## ofx importer
Vanial ofx importer that:

- uses ofxtools for all of the parsing
- extracts prices


## ideas

### Dynamic import.py
Make CONFIG an iterable that introspects existing file (or loaded file?).

Each account could have it's own import meta-data.  The Pros are:

* We don't "loose" accounts
* Less work keeping Multiple account files in sync with importers
* problem: If the importer changes over time?
    * this might not be an issue after the initial loading.

### Roundtrip Some of the files

Create a "Sorter" based on:

    YYYY, Account, MM, DD, meta['sort']

* each year could be it's own bean file (or folder?)
* At the start of the year a simple pad/balance can give a sane starting point
* intra-Year accounts can be opened/closed, but generally are manged in the root file.

### Duplicate Entry problem

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

### Beans as a Journal

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
