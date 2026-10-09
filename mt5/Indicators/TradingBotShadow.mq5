#property copyright "TradingBot"
#property version "1.00"
#property description "Read-only SHADOW monitor. No broker orders, no keys, no DLLs."
#property indicator_chart_window
#property indicator_plots 0
#property indicator_buffers 0

input string StrategyFilter = "all"; // all, opening_range, trend_pullback, compression_breakout, liquidity_sweep
input bool ShowLevels = true;
input int PanelX = 12;
input int PanelY = 25;
input int FontSize = 9;
string Prefix = "TBShadow_";

string SafeSymbol(string value)
{
   string out="";
   for(int i=0;i<StringLen(value);i++)
   {
      ushort c=StringGetCharacter(value,i);
      bool safe=(c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9') || c=='_' || c=='.' || c=='-';
      out += safe ? StringSubstr(value,i,1) : "_";
   }
   return out;
}

void Label(int row,string text,color ink)
{
   string name=Prefix+"panel_"+IntegerToString(row);
   ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,PanelX+10);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,PanelY+8+row*18);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,FontSize);
   ObjectSetInteger(0,name,OBJPROP_COLOR,ink);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
}

void Background(int rows)
{
   string name=Prefix+"background";
   ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,PanelX);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,PanelY);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,640);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,rows*18+18);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,clrBlack);
   ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrDimGray);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
}

void ClearLevels() { ObjectsDeleteAll(0,Prefix+"level_"); }

void Notice(string message)
{
   ClearLevels();
   ObjectsDeleteAll(0,Prefix+"panel_");
   Background(3);
   Label(0,"TradingBot | SHADOW | keine Orders",clrDeepSkyBlue);
   Label(1,message,clrOrange);
   Label(2,"Virtuelle Beobachtung; keine echten Positionen",clrSilver);
   ChartRedraw();
}

void Level(int index,string strategy,string kind,double price,color ink)
{
   if(price<=0 || !MathIsValidNumber(price)) return;
   string name=Prefix+"level_"+IntegerToString(index)+"_"+kind;
   string caption=strategy+" SHADOW "+kind+" "+DoubleToString(price,_Digits);
   ObjectCreate(0,name,OBJ_HLINE,0,0,price);
   ObjectSetDouble(0,name,OBJPROP_PRICE,price);
   ObjectSetInteger(0,name,OBJPROP_COLOR,ink);
   ObjectSetInteger(0,name,OBJPROP_STYLE,STYLE_DASH);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetString(0,name,OBJPROP_TEXT,caption);
   ObjectSetString(0,name,OBJPROP_TOOLTIP,caption+" | kein Brokerauftrag");
   string tag=name+"_text";
   ObjectCreate(0,tag,OBJ_TEXT,0,TimeCurrent(),price);
   ObjectMove(0,tag,0,TimeCurrent(),price);
   ObjectSetInteger(0,tag,OBJPROP_COLOR,ink);
   ObjectSetInteger(0,tag,OBJPROP_FONTSIZE,8);
   ObjectSetInteger(0,tag,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,tag,OBJPROP_SELECTABLE,false);
   ObjectSetString(0,tag,OBJPROP_TEXT,caption);
}

void Refresh()
{
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   { Notice("Anzeige nur auf dem Demokonto verfuegbar"); return; }
   string path="TradingBotShadow\\"+SafeSymbol(_Symbol)+".csv";
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE,0,CP_UTF8);
   if(h==INVALID_HANDLE)
   { Notice("Warte auf Python-Feed fuer "+_Symbol); return; }
   string lines[];
   while(!FileIsEnding(h) && ArraySize(lines)<32)
   {
      string line=FileReadString(h);
      if(StringLen(line)==0) continue;
      int n=ArraySize(lines); ArrayResize(lines,n+1); lines[n]=line;
   }
   FileClose(h);
   int total=ArraySize(lines);
   string head[],tail[];
   if(total<2 || StringSplit(lines[0],';',head)!=10 || StringSplit(lines[total-1],';',tail)!=2)
   { Notice("Chart-Feed unvollstaendig; warte auf naechsten Frame"); return; }
   if(head[0]!="HEADER" || head[1]!="1" || tail[0]!="END" || (int)StringToInteger(tail[1])!=total-1)
   { Notice("Chart-Feed ungueltig"); return; }
   string account=AccountInfoString(ACCOUNT_SERVER)+":"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   if(head[2]!=_Symbol || head[3]!=account)
   { Notice("Feed passt nicht zum Chart/Demokonto"); return; }
   // Validate every row before rendering a snapshot.
   int agent_count=0;
   for(int i=1;i<total-1;i++)
   {
      string p[]; int n=StringSplit(lines[i],';',p);
      if(n==5 && p[0]=="AGENT") agent_count++;
      else if(n==12 && p[0]=="CANDIDATE")
      {
         if(p[3]!="long" && p[3]!="short") { Notice("Ungueltige Kandidatenrichtung"); return; }
         for(int k=4;k<12;k++)
            if(!MathIsValidNumber(StringToDouble(p[k]))) { Notice("Ungueltige Kandidatendaten"); return; }
      }
      else { Notice("Ungueltige Feed-Zeile"); return; }
   }
   if(agent_count!=(int)StringToInteger(head[9])) { Notice("Agent-Frame unvollstaendig"); return; }
   double age=(double)TimeGMT()-StringToDouble(head[4]);
   if(age>30 || age< -2) { Notice("Feed veraltet/gestoppt oder Uhrzeit falsch"); return; }
   double quote_age=(double)TimeGMT()-StringToDouble(head[5]);
   bool quote_ok=StringToDouble(head[5])>0 && quote_age>=-2 && quote_age<=60;
   double analysis_age=(double)TimeGMT()-StringToDouble(head[6]);
   bool analysis_ok=StringToDouble(head[6])>0 && analysis_age>=-2 && analysis_age<=600;
   ClearLevels();
   ObjectsDeleteAll(0,Prefix+"panel_");
   Background(20);
   Label(0,"TradingBot | SHADOW | ORDERS GESPERRT",clrDeepSkyBlue);
   Label(1,_Symbol+" | M5-Auswertung | Regime: "+head[7],clrWhite);
   Label(2,head[8],clrOrange);
   Label(3,"Feed: "+DoubleToString(age,0)+"s | Kurs: "+DoubleToString(quote_age,0)+"s | Analyse: "+
         (StringToDouble(head[6])>0 ? DoubleToString(analysis_age,0)+"s" : "wartet"),
         quote_ok && analysis_ok ? clrLimeGreen : clrOrange);
   Label(4,"Agent            Richtung      Konf. Risiko (heuristisch)",clrSilver);
   int row=5,candidates=0;
   for(int i=1;i<total-1;i++)
   {
      string p[]; StringSplit(lines[i],';',p);
      if(p[0]=="AGENT")
      {
         Label(row++,StringFormat("%-16s %-12s %5.0f %5.0f",p[1],p[2],StringToDouble(p[3]),StringToDouble(p[4])),
               p[2]=="no_trade" ? clrOrange : clrWhite);
      }
   }
   Label(row++,"Virtuelle Kandidaten: Entry blau | SL rot | TP gruen",clrSilver);
   for(int i=1;i<total-1;i++)
   {
      string p[]; StringSplit(lines[i],';',p);
      if(p[0]!="CANDIDATE" || (StrategyFilter!="all" && p[2]!=StrategyFilter)) continue;
      candidates++;
      Label(row++,p[2]+" "+p[3]+" | Score "+p[8]+" | virtuell "+DoubleToString(StringToDouble(p[9]),2)+"R",clrWhite);
      if(ShowLevels && quote_ok)
      {
         Level(candidates,p[2],"Entry",StringToDouble(p[4]),clrDeepSkyBlue);
         Level(candidates,p[2],"SL",StringToDouble(p[5]),clrTomato);
         Level(candidates,p[2],"TP1",StringToDouble(p[6]),clrLimeGreen);
         Level(candidates,p[2],"TP2",StringToDouble(p[7]),clrSeaGreen);
      }
   }
   if(candidates==0) Label(row++,"Keine aktiven virtuellen Kandidaten fuer diesen Filter",clrSilver);
   Label(row++,"Nur Stichproben; ohne echte Fills, Gebuehren oder Slippage",clrSilver);
   Background(row);
   ChartRedraw();
}

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME,"TradingBot SHADOW");
   if(!EventSetTimer(2)) return INIT_FAILED;
   Refresh();
   return INIT_SUCCEEDED;
}
void OnTimer() { Refresh(); }
void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0,Prefix);
   ChartRedraw();
}
int OnCalculate(const int rates_total,const int prev_calculated,const datetime &time[],
                const double &open[],const double &high[],const double &low[],const double &close[],
                const long &tick_volume[],const long &volume[],const int &spread[])
{
   return rates_total;
}
