"""Reproduce newly found failures in the supplied engine and corrected behavior."""
import json
import reference_engine as old
import engine as new

def check(mod):
    opts=mod.Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True)
    g=mod.Game(1,opts);a,b=g.cs['Tropia'],g.cs['Grainia'];uid=g.ids(a,'banana')[0]
    before=g.cs['Technia'].cash
    ok=g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[uid]}],('Technia',a.name,10),'market','payer')
    third={'accepted':ok,'third_country_cash_loss':before-g.cs['Technia'].cash}
    g=mod.Game(1,opts);g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia'];g.mint(a,'machine',1);uid=g.ids(a,'machine')[0]
    g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[uid]}],(b.name,a.name,50),'direct','d')
    g.mark_use(b,uid,'equipment');first=b.import_slots;g.mark_use(b,uid,'equipment')
    repeated={'first':first,'after_repeated_use':b.import_slots}
    g=mod.Game(1,opts);g.r=1;c=g.cs['Tropia'];g.mint(c,'electronics',1)
    g.make_order(c,g.ids(c,'electronics'),80)
    before=(len(g.transactions),c.cash)
    free=g.settle_transaction([{'seller':c.name,'buyer':'Grainia','ids':g.ids(c,'electronics',False)}],None,'market','free')
    return {'third_party_charge':third,'duplicate_use_episode':repeated,'free_market_transfer_accepted':free}

if __name__=='__main__':
    out={'previous':check(old),'revised':check(new)}
    print(json.dumps(out,indent=2))
    open('results/audit_previous.json','w').write(json.dumps(out,indent=2))
