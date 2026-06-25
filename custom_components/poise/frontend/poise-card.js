/* poise-card 0.80.0 — bundled, served by the Poise integration (ADR-0040) */
var K=globalThis,W=K.ShadowRoot&&(K.ShadyCSS===void 0||K.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,et=Symbol(),ft=new WeakMap,U=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==et)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(W&&t===void 0){let s=e!==void 0&&e.length===1;s&&(t=ft.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&ft.set(e,t))}return t}toString(){return this.cssText}},gt=i=>new U(typeof i=="string"?i:i+"",void 0,et),H=(i,...t)=>{let e=i.length===1?i[0]:t.reduce((s,n,o)=>s+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+i[o+1],i[0]);return new U(e,i,et)},_t=(i,t)=>{if(W)i.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let s=document.createElement("style"),n=K.litNonce;n!==void 0&&s.setAttribute("nonce",n),s.textContent=e.cssText,i.appendChild(s)}},st=W?i=>i:i=>i instanceof CSSStyleSheet?(t=>{let e="";for(let s of t.cssRules)e+=s.cssText;return gt(e)})(i):i;var{is:zt,defineProperty:Lt,getOwnPropertyDescriptor:Ft,getOwnPropertyNames:Vt,getOwnPropertySymbols:Bt,getPrototypeOf:jt}=Object,q=globalThis,vt=q.trustedTypes,Kt=vt?vt.emptyScript:"",Wt=q.reactiveElementPolyfillSupport,T=(i,t)=>i,nt={toAttribute(i,t){switch(t){case Boolean:i=i?Kt:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,t){let e=i;switch(t){case Boolean:e=i!==null;break;case Number:e=i===null?null:Number(i);break;case Object:case Array:try{e=JSON.parse(i)}catch{e=null}}return e}},$t=(i,t)=>!zt(i,t),yt={attribute:!0,type:String,converter:nt,reflect:!1,useDefault:!1,hasChanged:$t};Symbol.metadata??=Symbol("metadata"),q.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=yt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let s=Symbol(),n=this.getPropertyDescriptor(t,s,e);n!==void 0&&Lt(this.prototype,t,n)}}static getPropertyDescriptor(t,e,s){let{get:n,set:o}=Ft(this.prototype,t)??{get(){return this[e]},set(r){this[e]=r}};return{get:n,set(r){let c=n?.call(this);o?.call(this,r),this.requestUpdate(t,c,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??yt}static _$Ei(){if(this.hasOwnProperty(T("elementProperties")))return;let t=jt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(T("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(T("properties"))){let e=this.properties,s=[...Vt(e),...Bt(e)];for(let n of s)this.createProperty(n,e[n])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[s,n]of e)this.elementProperties.set(s,n)}this._$Eh=new Map;for(let[e,s]of this.elementProperties){let n=this._$Eu(e,s);n!==void 0&&this._$Eh.set(n,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let s=new Set(t.flat(1/0).reverse());for(let n of s)e.unshift(st(n))}else t!==void 0&&e.push(st(t));return e}static _$Eu(t,e){let s=e.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return _t(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){let s=this.constructor.elementProperties.get(t),n=this.constructor._$Eu(t,s);if(n!==void 0&&s.reflect===!0){let o=(s.converter?.toAttribute!==void 0?s.converter:nt).toAttribute(e,s.type);this._$Em=t,o==null?this.removeAttribute(n):this.setAttribute(n,o),this._$Em=null}}_$AK(t,e){let s=this.constructor,n=s._$Eh.get(t);if(n!==void 0&&this._$Em!==n){let o=s.getPropertyOptions(n),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:nt;this._$Em=n;let c=r.fromAttribute(e,o.type);this[n]=c??this._$Ej?.get(n)??c,this._$Em=null}}requestUpdate(t,e,s,n=!1,o){if(t!==void 0){let r=this.constructor;if(n===!1&&(o=this[t]),s??=r.getPropertyOptions(t),!((s.hasChanged??$t)(o,e)||s.useDefault&&s.reflect&&o===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,s))))return;this.C(t,e,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:n,wrapped:o},r){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),o!==!0||r!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),n===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[n,o]of this._$Ep)this[n]=o;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[n,o]of s){let{wrapped:r}=o,c=this[n];r!==!0||this._$AL.has(n)||c===void 0||this.C(n,void 0,o,c)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(e)):this._$EM()}catch(s){throw t=!1,this._$EM(),s}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[T("elementProperties")]=new Map,w[T("finalized")]=new Map,Wt?.({ReactiveElement:w}),(q.reactiveElementVersions??=[]).push("2.1.2");var dt=globalThis,bt=i=>i,G=dt.trustedTypes,wt=G?G.createPolicy("lit-html",{createHTML:i=>i}):void 0,kt="$lit$",x=`lit$${Math.random().toFixed(9).slice(2)}$`,Pt="?"+x,qt=`<${Pt}>`,E=document,O=()=>E.createComment(""),D=i=>i===null||typeof i!="object"&&typeof i!="function",pt=Array.isArray,Gt=i=>pt(i)||typeof i?.[Symbol.iterator]=="function",it=`[ 	
\f\r]`,N=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,xt=/-->/g,At=/>/g,C=RegExp(`>|${it}(?:([^\\s"'>=/]+)(${it}*=${it}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ct=/'/g,St=/"/g,Mt=/^(?:script|style|textarea|title)$/i,ht=i=>(t,...e)=>({_$litType$:i,strings:t,values:e}),u=ht(1),pe=ht(2),he=ht(3),k=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),Et=new WeakMap,S=E.createTreeWalker(E,129);function Rt(i,t){if(!pt(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return wt!==void 0?wt.createHTML(t):t}var Xt=(i,t)=>{let e=i.length-1,s=[],n,o=t===2?"<svg>":t===3?"<math>":"",r=N;for(let c=0;c<e;c++){let a=i[c],l,f,p=-1,_=0;for(;_<a.length&&(r.lastIndex=_,f=r.exec(a),f!==null);)_=r.lastIndex,r===N?f[1]==="!--"?r=xt:f[1]!==void 0?r=At:f[2]!==void 0?(Mt.test(f[2])&&(n=RegExp("</"+f[2],"g")),r=C):f[3]!==void 0&&(r=C):r===C?f[0]===">"?(r=n??N,p=-1):f[1]===void 0?p=-2:(p=r.lastIndex-f[2].length,l=f[1],r=f[3]===void 0?C:f[3]==='"'?St:Ct):r===St||r===Ct?r=C:r===xt||r===At?r=N:(r=C,n=void 0);let $=r===C&&i[c+1].startsWith("/>")?" ":"";o+=r===N?a+qt:p>=0?(s.push(l),a.slice(0,p)+kt+a.slice(p)+x+$):a+x+(p===-2?c:$)}return[Rt(i,o+(i[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]},I=class i{constructor({strings:t,_$litType$:e},s){let n;this.parts=[];let o=0,r=0,c=t.length-1,a=this.parts,[l,f]=Xt(t,e);if(this.el=i.createElement(l,s),S.currentNode=this.el.content,e===2||e===3){let p=this.el.content.firstChild;p.replaceWith(...p.childNodes)}for(;(n=S.nextNode())!==null&&a.length<c;){if(n.nodeType===1){if(n.hasAttributes())for(let p of n.getAttributeNames())if(p.endsWith(kt)){let _=f[r++],$=n.getAttribute(p).split(x),b=/([.?@])?(.*)/.exec(_);a.push({type:1,index:o,name:b[2],strings:$,ctor:b[1]==="."?rt:b[1]==="?"?at:b[1]==="@"?ct:M}),n.removeAttribute(p)}else p.startsWith(x)&&(a.push({type:6,index:o}),n.removeAttribute(p));if(Mt.test(n.tagName)){let p=n.textContent.split(x),_=p.length-1;if(_>0){n.textContent=G?G.emptyScript:"";for(let $=0;$<_;$++)n.append(p[$],O()),S.nextNode(),a.push({type:2,index:++o});n.append(p[_],O())}}}else if(n.nodeType===8)if(n.data===Pt)a.push({type:2,index:o});else{let p=-1;for(;(p=n.data.indexOf(x,p+1))!==-1;)a.push({type:7,index:o}),p+=x.length-1}o++}}static createElement(t,e){let s=E.createElement("template");return s.innerHTML=t,s}};function P(i,t,e=i,s){if(t===k)return t;let n=s!==void 0?e._$Co?.[s]:e._$Cl,o=D(t)?void 0:t._$litDirective$;return n?.constructor!==o&&(n?._$AO?.(!1),o===void 0?n=void 0:(n=new o(i),n._$AT(i,e,s)),s!==void 0?(e._$Co??=[])[s]=n:e._$Cl=n),n!==void 0&&(t=P(i,n._$AS(i,t.values),n,s)),t}var ot=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:s}=this._$AD,n=(t?.creationScope??E).importNode(e,!0);S.currentNode=n;let o=S.nextNode(),r=0,c=0,a=s[0];for(;a!==void 0;){if(r===a.index){let l;a.type===2?l=new z(o,o.nextSibling,this,t):a.type===1?l=new a.ctor(o,a.name,a.strings,this,t):a.type===6&&(l=new lt(o,this,t)),this._$AV.push(l),a=s[++c]}r!==a?.index&&(o=S.nextNode(),r++)}return S.currentNode=E,n}p(t){let e=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}},z=class i{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,n){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=n,this._$Cv=n?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=P(this,t,e),D(t)?t===d||t==null||t===""?(this._$AH!==d&&this._$AR(),this._$AH=d):t!==this._$AH&&t!==k&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):Gt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==d&&D(this._$AH)?this._$AA.nextSibling.data=t:this.T(E.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:s}=t,n=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=I.createElement(Rt(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===n)this._$AH.p(e);else{let o=new ot(n,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(t){let e=Et.get(t.strings);return e===void 0&&Et.set(t.strings,e=new I(t)),e}k(t){pt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,s,n=0;for(let o of t)n===e.length?e.push(s=new i(this.O(O()),this.O(O()),this,this.options)):s=e[n],s._$AI(o),n++;n<e.length&&(this._$AR(s&&s._$AB.nextSibling,n),e.length=n)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let s=bt(t).nextSibling;bt(t).remove(),t=s}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},M=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,n,o){this.type=1,this._$AH=d,this._$AN=void 0,this.element=t,this.name=e,this._$AM=n,this.options=o,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=d}_$AI(t,e=this,s,n){let o=this.strings,r=!1;if(o===void 0)t=P(this,t,e,0),r=!D(t)||t!==this._$AH&&t!==k,r&&(this._$AH=t);else{let c=t,a,l;for(t=o[0],a=0;a<o.length-1;a++)l=P(this,c[s+a],e,a),l===k&&(l=this._$AH[a]),r||=!D(l)||l!==this._$AH[a],l===d?t=d:t!==d&&(t+=(l??"")+o[a+1]),this._$AH[a]=l}r&&!n&&this.j(t)}j(t){t===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},rt=class extends M{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===d?void 0:t}},at=class extends M{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==d)}},ct=class extends M{constructor(t,e,s,n,o){super(t,e,s,n,o),this.type=5}_$AI(t,e=this){if((t=P(this,t,e,0)??d)===k)return;let s=this._$AH,n=t===d&&s!==d||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,o=t!==d&&(s===d||n);n&&this.element.removeEventListener(this.name,this,s),o&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},lt=class{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){P(this,t)}};var Jt=dt.litHtmlPolyfillSupport;Jt?.(I,z),(dt.litHtmlVersions??=[]).push("3.3.3");var Ut=(i,t,e)=>{let s=e?.renderBefore??t,n=s._$litPart$;if(n===void 0){let o=e?.renderBefore??null;s._$litPart$=n=new z(t.insertBefore(O(),o),o,void 0,e??{})}return n._$AI(i),n};var ut=globalThis,y=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Ut(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return k}};y._$litElement$=!0,y.finalized=!0,ut.litElementHydrateSupport?.({LitElement:y});var Zt=ut.litElementPolyfillSupport;Zt?.({LitElement:y});(ut.litElementVersions??=[]).push("4.2.2");function Yt(i,t,e){return Math.min(Math.max(i,t),e)}function X(i,t,e){return e<=t?.5:Yt((i-t)/(e-t),0,1)}function Qt(i,t,e){if(i==null)return"unknown";if(i<t)return"below";if(i>e)return"above";let s=e-t;if(s<=0)return"in_band";let n=(i-t)/s;return n<.25?"cool_edge":n>.75?"warm_edge":"in_band"}function Ht(i){let{operative:t,setpoint:e,low:s,high:n}=i;if(s==null||n==null||n<=s)return null;let o=s-1.5,r=n+1.5;return{low:s,high:n,span:n-s,operative:t,setpoint:e,category:i.category??"",verdict:Qt(t,s,n),axisLow:o,axisHigh:r,lowFrac:X(s,o,r),highFrac:X(n,o,r),operativeFrac:t==null?null:X(t,o,r),setpointFrac:e==null?null:X(e,o,r)}}var Tt={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload"},te={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden"};function m(i,t){return((i??"en").toLowerCase().startsWith("de")?te:Tt)[t]??Tt[t]??t}var ee=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"show_shadow",selector:{boolean:{}}},{name:"compact",selector:{boolean:{}}}],J=class extends y{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?u``:u`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${ee}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};J.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",J);var Z="0.80.0",Nt=!1;function se(){let i=()=>location.reload();"caches"in window?caches.keys().then(t=>Promise.all(t.map(e=>caches.delete(e)))).then(i,i):i()}async function Y(i,t){if(!(Nt||!t?.connection)){Nt=!0;try{let e=await t.connection.sendMessagePromise({type:"poise/card_version"});if(e?.version&&e.version!==Z){let s=t.locale?.language;i.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${m(s,"update_msg")} (${Z} \u2192 ${e.version})`,duration:-1,dismissable:!0,action:{text:m(s,"reload"),action:se}},bubbles:!0,composed:!0}))}}catch{}}}function L(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var F=class extends y{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(t){return{type:"custom:poise-system-card",entity:Object.keys(t.states).find(s=>s.startsWith("binary_sensor.")&&t.states[s].attributes.zone_count!==void 0)??""}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config=t}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&Y(this,this.hass)}shouldUpdate(t){if(t.has("_config"))return!0;let e=t.get("hass");return!e||!this._config?.entity?!0:e.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}render(){let t=this.hass?.locale?.language,e=this._config?.entity,s=e?this.hass.states[e]:void 0;if(!s)return u`<ha-card
        ><div class="empty">${m(t,"no_system")}</div></ha-card
      >`;let n=s.attributes,o=s.state==="on",r=L(n.flow_target),c=L(n.shed_count)??0,a=n.source_grants??{},l=Object.keys(a);return u`<ha-card .header=${m(t,"sys_title")}>
      <div class="wrap" @click=${this._moreInfo}>
        <div class="state ${o?"on":""}">
          <ha-icon icon=${o?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${o?m(t,"demand_on"):m(t,"demand_off")}</span>
          ${n.frost_override?u`<em class="frost">${m(t,"frost")}</em>`:d}
        </div>
        <div class="stats">
          <div>
            <strong>${L(n.active_zones)??0}</strong
            ><span>${m(t,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${L(n.controlling_zones)??0}/${L(n.zone_count)??0}</strong
            ><span>${m(t,"zones")}</span>
          </div>
          ${r!=null?u`<div>
                <strong>${r.toFixed(0)}°</strong><span>${m(t,"flow")}</span>
              </div>`:d}
          ${c>0?u`<div>
                <strong>${c}</strong><span>${m(t,"shed")}</span>
              </div>`:d}
        </div>
        ${l.length?u`<div class="grants">
              ${l.map(f=>u`<span class="chip">${f}: ${a[f]}</span>`)}
            </div>`:d}
      </div>
    </ha-card>`}};F.properties={hass:{},_config:{state:!0}},F.styles=H`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var Q=class extends y{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?u``:u`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};Q.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",Q);customElements.get("poise-system-card")||customElements.define("poise-system-card",F);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function Ot(i,t,e){return Math.min(Math.max(i,t),e)}function Dt(i,t,e,s=300,n=90,o=1){let r=[];for(let g of i)g.op!=null&&r.push(g.op),g.sp!=null&&r.push(g.sp);if(t!=null&&r.push(t),e!=null&&r.push(e),r.length===0||i.length===0)return null;let c=Math.min(...r)-o,a=Math.max(...r)+o,l=i[0].t,p=i[i.length-1].t-l||1,_=a-c||1,$=g=>(g-l)/p*s,b=g=>n-(g-c)/_*n,R=g=>i.filter(A=>g(A)!=null).map(A=>`${$(A.t).toFixed(1)},${b(g(A)).toFixed(1)}`).join(" ");return{width:s,height:n,opPath:R(g=>g.op),spPath:R(g=>g.sp),bandTop:e==null?0:Ot(b(e),0,n),bandBottom:t==null?n:Ot(b(t),0,n),vMin:c,vMax:a}}var v={min:16,max:28,start:135,sweep:270};function ne(i,t,e){return Math.min(Math.max(i,t),e)}function B(i,t=v){let e=ne((i-t.min)/(t.max-t.min),0,1);return t.start+e*t.sweep}function ie(i,t=v){let e=i;for(;e<t.start;)e+=360;for(;e>=t.start+360;)e-=360;if(e<=t.start+t.sweep)return e;let s=e-(t.start+t.sweep);return t.start+360-e<s?t.start:t.start+t.sweep}function oe(i,t=v){let s=(ie(i,t)-t.start)/t.sweep;return t.min+s*(t.max-t.min)}function V(i,t,e,s){let n=s*Math.PI/180;return{x:i+e*Math.cos(n),y:t+e*Math.sin(n)}}function mt(i,t,e,s,n){if(n<=s)return"";let o=V(i,t,e,s),r=V(i,t,e,n),c=n-s>180?1:0;return`M ${o.x.toFixed(2)} ${o.y.toFixed(2)} A ${e} ${e} 0 ${c} 1 ${r.x.toFixed(2)} ${r.y.toFixed(2)}`}function It(i,t,e=v){let s=Math.atan2(t,i)*180/Math.PI;return s<0&&(s+=360),oe(s,e)}function re(i){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[i]??"mdi:tune"}function h(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var j=class extends y{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=v}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(e){return{type:"custom:poise-card",entity:Object.keys(e.states).find(n=>n.startsWith("climate.")&&e.states[n].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(e){if(!e)throw new Error("Invalid configuration");if(e.entity&&!e.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...e}}getCardSize(){return 4}getGridOptions(){return this._config?.compact?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(e){if(this._dragging||e.has("_config"))return!0;let s=e.get("hass");return!s||!this._config?.entity?!0:s.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(e){let s=this._config.entity;if(!s)return;let n=this.hass.states[s];if(!n)return;let o=h(n.attributes.target_temperature_step)??.5,r=h(n.attributes.heat_sp)??h(n.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:s,temperature:Math.round((r+e*o)*10)/10})}updated(){this.hass&&Y(this,this.hass);let e=this._config?.entity;e&&this.hass&&this._histFor!==e&&(this._histFor=e,this._loadHistory(e))}async _loadHistory(e){if(!this.hass.connection)return;let s=new Date,n=new Date(s.getTime()-24*3600*1e3);try{let r=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:n.toISOString(),end_time:s.toISOString(),entity_ids:[e],minimal_response:!1,no_attributes:!1}))?.[e]??[],c={},a=[];for(let l of r){l.a&&(c={...c,...l.a});let f=(h(l.lu)??h(l.lc)??0)*1e3;a.push({t:f,op:h(c.operative_temperature)??h(c.current_temperature),sp:h(c.heat_sp)??h(c.temperature)})}this._history=a,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(e,s){let n=Dt(this._history,e,s,300,80);return n?u`<svg
      class="chart"
      viewBox="0 0 ${n.width} ${n.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${n.bandTop}
        width=${n.width}
        height=${Math.max(0,n.bandBottom-n.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${n.spPath} class="csp"></polyline>
      <polyline points=${n.opPath} class="cop"></polyline>
    </svg>`:d}render(){let e=this.hass?.locale?.language,s=this._config?.entity,n=s?this.hass.states[s]:void 0;if(!n)return u`<ha-card
        ><div class="empty">${m(e,"no_entity")}</div></ha-card
      >`;let o=n.attributes,r=h(o.operative_temperature)??h(o.current_temperature),c=h(o.heat_sp)??h(o.temperature),a=Ht({operative:r,setpoint:c,low:h(o.comfort_low),high:h(o.comfort_high),category:o.category??null});return u`<ha-card .header=${o.friendly_name??"Poise"}>
      <div class="wrap ${this._config.compact?"compact":""}">
        ${this._dial(o,e)}
        <div class="verdict">
          ${a?m(e,a.verdict):m(e,"unknown")}
          ${a?.category?u`<span class="cat">Kat. ${a.category}</span>`:d}
        </div>
        ${this._config.compact?d:u`${this._control(this._pending??c,e)}
              ${this._chart(h(o.comfort_low),h(o.comfort_high))}
              ${this._chips(o,e)}`}
        ${this._learn(o,e)}
      </div>
    </ha-card>`}_dial(e,s){let n=h(e.operative_temperature)??h(e.current_temperature),o=h(e.heat_sp)??h(e.temperature),r={min:h(e.min_temp)??v.min,max:h(e.max_temp)??v.max,start:v.start,sweep:v.sweep};this._dialCfg=r.max>r.min?r:v;let c=this._pending??o??n??this._dialCfg.min,a=h(e.comfort_low),l=h(e.comfort_high),f=100,p=100,_=80,$=mt(f,p,_,v.start,v.start+v.sweep),b=a!=null&&l!=null?mt(f,p,_,B(Math.min(a,l),this._dialCfg),B(Math.max(a,l),this._dialCfg)):"",R=String(e.hvac_action??""),g=R==="heating"?"heat":R==="cooling"?"cool":"",A=V(f,p,_,B(c,this._dialCfg)),tt=n!=null?V(f,p,_,B(n,this._dialCfg)):null;return u`<div class="dialwrap">
      <svg
        class="dial"
        viewBox="0 0 200 200"
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${$}></path>
        <path class="bandarc" d=${b}></path>
        <circle
          class="opdot"
          cx=${(tt?.x??0).toFixed(1)}
          cy=${(tt?.y??0).toFixed(1)}
          r=${tt?5:0}
        ></circle>
        <circle class="handle ${g}" cx=${A.x.toFixed(1)} cy=${A.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div class="ctrclick" @click=${this._moreInfo}>
          <div class="op">${n!=null?n.toFixed(1):"\u2014"}<span>°C</span></div>
          <div class="soll">${m(s,"setpoint")} <b>${c.toFixed(1)}°</b></div>
        </div>
      </div>
    </div>`}_fromPointer(e,s){let n=s.getBoundingClientRect();if(!n.width||!this._config.entity)return;let o=(e.clientX-n.left)/n.width*200-100,r=(e.clientY-n.top)/n.height*200-100,c=h(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(It(o,r,this._dialCfg)/c)*c,this.requestUpdate()}_onDown(e){if(!this._config.entity)return;e.preventDefault();let s=e.currentTarget;s.setPointerCapture(e.pointerId),this._dragging=!0,this._fromPointer(e,s)}_onMove(e){this._dragging&&this._fromPointer(e,e.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let e=this._pending;this._pending=null,e!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:e}),this.requestUpdate()}_control(e,s){return u`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${m(s,"setpoint")}</span
        ><strong>${e!=null?e.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_chips(e,s){let n=[];e.preheating&&n.push(this._chip("mdi:fire-circle",m(s,"preheating"),e.minutes_to_comfort,s)),e.coasting&&n.push(this._chip("mdi:coffee",m(s,"coasting"),e.minutes_to_setback,s)),e.window_open&&n.push(this._chip("mdi:window-open",m(s,e.window_auto_detected?"window_auto":"window"))),e.window_bypass&&n.push(this._chip("mdi:window-closed-variant",m(s,"bypass")));let o=e.preset==null?"none":String(e.preset);o!=="none"&&n.push(this._chip(re(o),m(s,o)||o)),e.heating_failure&&n.push(this._chip("mdi:alert",m(s,"failure")));let r=e.binding_lower_cause;return r&&r!=="en16798"&&n.push(this._chip("mdi:shield-alert",String(r))),n.length?u`<div class="chips" @click=${this._moreInfo}>${n}</div>`:d}_chip(e,s,n,o){let r=h(n);return u`<div class="chip">
      <ha-icon icon=${e}></ha-icon><span>${s}</span>
      ${r!=null?u`<em>${Math.round(r)} ${m(o,"min_left")}</em>`:d}
    </div>`}_learn(e,s){let n=h(e.confidence),o=this._config.show_shadow&&(e.mpc_active||e.tpi_active||e.pi_active),r=h(e.pi_setpoint),c=h(e.mpc_setpoint),a=e.tpi_active?`TPI ${Math.round(h(e.tpi_valve_percent)??0)}%`:e.pi_active&&r!=null?`PI ${r.toFixed(1)}\xB0`:e.mpc_active&&c!=null?`MPC ${c.toFixed(1)}\xB0`:"";return u`<div class="learn">
      ${n!=null?u`<div class="bar">
            <i style="width:${(n*100).toFixed(0)}%"></i>
          </div>
          <span>${m(s,"learning")} ${(n*100).toFixed(0)}%</span>`:d}
      ${o?u`<div class="pill">
            ${m(s,"shadow")}${a?u` · ${a}`:d}
          </div>`:d}
    </div>`}};j.properties={hass:{},_config:{state:!0}},j.styles=H`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",j);console.info(`%c POISE-CARD ${Z} `,"background:#2196f3;color:#fff");export{j as PoiseCard};
