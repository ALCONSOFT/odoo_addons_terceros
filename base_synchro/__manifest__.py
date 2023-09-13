# See LICENSE file for full copyright and licensing details.

{
    "name": "AlconSoft - Multi-DB Synchronization",
    "version": "14.0-23.09.13",
    "category": "Tools",
    "license": "AGPL-3",
    "summary": "Multi-DB Synchronization",
    "author": "OpenERP SA, Serpent Consulting Services Pvt. Ltd. - Alconsoft",
    "website": "http://www.serpentcs.com",
    "maintainer": "Alconsoft",
    "images": ["static/description/Synchro.png"],
    "depends": ["base","stock", "jobcostphasecat"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/base_synchro_view.xml",
        "wizard/viewsynchro.xml",
        "views/base_synchro_view.xml",
        "views/res_request_view.xml",
    ],
    "installable": True,
}
