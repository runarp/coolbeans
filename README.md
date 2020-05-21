# coolbeans -- Tools for beancount

A collection of utilities and importers I use for my beancount workflow.

I'll try to keep this project "generic" and "configurable" so, perhaps, someone
else could use it.


## Usage

There are two command-line utilities so far.  cool-organizer and cool-match. 
There are also a few importers and at least one plugin.

###  cool-organizer
cool-organizer will modify a file in-place, filing new entries:

  cool-organizer -e root.bean -m 2020.bean new_entries.bean -y 2020

Read the root.bean and file entries from new_entires.bean into the
2020.bean.  the -y filter enforces the filing to ignore any other years from
the new_entries.  This is quite workflow specific.

### coolbeans.matcher plugin

While the workflow is still a wip. I've had good luck using the matcher as a
pure plugin.  This has an interesting effect where I can "preview" the modified
transaction in fava without changing any code.  The record is also written to an
output file (specified in the configuration).  In my root bean file I have:

    plugin "coolbeans.matcher"
    2018-06-14 custom "coolbeans" "rules-file"  "./rules.yaml"
    2018-06-14 custom "coolbeans" "output-file"  "./incoming/matches.bean"
    2018-06-14 custom "coolbeans" "gen-rules-file"  "./incoming/new-rules.yaml"

matches.bean is useful to view the transactions.  I then use cool-organizer to
replace the entries.  This will probably evolve.  The nice thing is running
fava in debug mode, you can get a live-preview of the regular expression
results as you write them.

The new-rules.yaml is more of a report of good candidates for which to write
rules (sorted by number of hits by narration).

### cool-match

Allows for applying a set of regex rules to an existing file.  This is very much
broken.

    cool-match -e 2020.bean -r rules.yaml > stagefile.bean

Then you can organize the entries:

    cool-organizer -e root.bean -m 2020.bean stagefile.bean -y 2020

## ib importer

This is a regular importer that implements most of the class (name files etc.).

The input files are XML generated from the Interactive Broker's IBFlex report.

Each transaction has an extra 'match-key' meta attribute, used for
de-duplication.

## ofx importer
Vanilla ofx importer that:

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
* For "transfer" records (Asset->Liability) or (Asset->Asset), we use a
  transfer account "Assets:Transfers"

    2020-04-24 ! "Payment Received"
      ofx-fitid: "75140210115007025646907108"
      ofx-type: "CREDIT"
      * Liabilities:CreditCard:Barklays:Aviator   63.49 USD
      T Assets:Transfers                         -63.49 USD
        account: Assets:Banks:BofA:Checking


### Beans as a Journal

This has been implemented with cool-organizer

If I sort each file purely by time (not by account). Things start to look more
like a "journal of your life" than a bunch of statements.  Each Day/Week/Month
becomes a section in a generated/managed files.  Ideally, we can still keep the
round-trip capabilities of the system.  But we have a fixed sorter.

Section headers are auto-generated:

* January
** Week 2
** Week 3
* February

Because we are forcing accounts, we have to white-list the Accounts that go
into the annual file?  (I want to exclude trading accounts)

### Filing Cabinet

*There's now an importer for this called 'statementfiling.py'*

With the importers, bean-file and the account hierarchy as folder structure we
have a pretty good foundation for a system to manage documents.  I'm not sure
where the limits of this might be (number of files, search etc).  Some tools
that might be interesting for my workflow are:

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

This can be optional, but use bean-file.
