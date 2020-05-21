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

Each account could have its own import meta-data.  The Pros are:

* We don't "loose" accounts
* Less work keeping Multiple account files in sync with importers
* problem: If the importer changes over time?
    * this might not be an issue after the initial loading.


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

### Roundtrip Some of the files

Create a "Sorter" based on:

    YYYY, Account, MM, DD, meta['sort']

* each year could be it's own bean file (or folder?)
* At the start of the year a simple pad/balance can give a sane starting point
* intra-Year accounts can be opened/closed, but generally are manged in the root file.

### Filing Cabinet

With the importers, bean-file and the account hierarchy as folder structure we
have a pretty good foundation for a system to manage documents.  I'm not sure
where the limits of this might be (number of files, search etc).  Some tools that
might be interesting for my workflow are:

* incoming folder monitor on Dropbox - My assistant can drop files into a folder
  and they could get files.
* slugs per account - with a slug we might be able to auto-file unknown files:
    
    YYYY-MM-DD-[slug]-[documenttype].pdf

Would get picked up by an importer and [slug] -> Account could be handled via a 
simple meta tag on open directive.

given:

  2010-01-01 open Assets:Employee:PettyCash:Jane
      :slug: "pettycashjane"

2020-02-03-pettycashjane-invoice.pdf  for example would get filed under the correct folder.

Of course we could have plugins auto-add a slug to Accounts or any number of
transformations.

It would also be interesting to see the date-range covered by a single input file.
This can be optional, but use bean-file:

2020-03-01.


#### 


